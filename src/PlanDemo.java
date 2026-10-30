import java.math.BigDecimal;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

/** Standalone teaching example. All identifiers and resources are synthetic. */
public class PlanDemo {
    record Candidate(long categoryId, long projectId, String name, Set<String> allowedUnits) {
        Candidate { allowedUnits = Set.copyOf(allowedUnits); }
    }
    record Choice(long categoryId, long projectId, String claimedName, String amount, String unit) {}
    record Item(long categoryId, long projectId, String name, BigDecimal amount, String unit) {}
    record Plan(List<Choice> choices) { Plan { choices = List.copyOf(choices); } }
    static class InvalidPlan extends RuntimeException {
        InvalidPlan(String message) { super(message); }
    }

    // Stricter than the project's item-filtering policy: any invalid item rejects the draft.
    static List<Item> validate(Plan plan, List<Candidate> library) {
        if (plan == null || plan.choices().isEmpty()) throw new InvalidPlan("empty plan");
        var byCategory = new HashMap<Long, Map<Long, Candidate>>();
        for (var c : library) {
            var projects = byCategory.computeIfAbsent(c.categoryId(), k -> new HashMap<>());
            if (projects.putIfAbsent(c.projectId(), c) != null)
                throw new IllegalStateException("duplicate candidate in source library");
        }
        var seen = new HashSet<String>();
        var result = new ArrayList<Item>();
        for (var choice : plan.choices()) {
            var candidate = byCategory.getOrDefault(choice.categoryId(), Map.of()).get(choice.projectId());
            if (candidate == null) throw new InvalidPlan("project not in selected category");
            if (!seen.add(choice.categoryId() + ":" + choice.projectId()))
                throw new InvalidPlan("duplicate selection");
            if (!candidate.allowedUnits().contains(choice.unit())) throw new InvalidPlan("invalid unit");
            if (choice.amount() == null || !choice.amount().matches("[0-9]+(?:\\.[0-9]+)?"))
                throw new InvalidPlan("amount must be a numeric string");
            var amount = new BigDecimal(choice.amount());
            if (amount.signum() <= 0) throw new InvalidPlan("amount must be positive");
            result.add(new Item(choice.categoryId(), choice.projectId(), candidate.name(), amount, choice.unit()));
        }
        return List.copyOf(result);
    }

    static List<Item> generate(Supplier<Plan> model, List<Candidate> library, int repairs) {
        if (repairs < 0 || repairs > 2) throw new IllegalArgumentException("repairs must be 0..2");
        for (int attempt = 0; ; attempt++) {
            Plan draft = model.get(); // transport failures are deliberately outside the repair catch
            try { return validate(draft, library); }
            catch (InvalidPlan e) { if (attempt == repairs) throw e; }
        }
    }

    enum Status { PENDING, RUNNING, SUCCEEDED }
    record Task(UUID executionId, Status status, String result) {}
    record Submission(Task task, boolean created) {}
    static class TaskStore {
        final ConcurrentHashMap<Long, Task> records = new ConcurrentHashMap<>();
        Submission submit(long planId) {
            // Atomic per planId, within this JVM only. No model call runs inside compute().
            boolean[] created = {false};
            Task task = records.compute(planId, (key, previous) -> {
                if (previous != null && previous.status() != Status.SUCCEEDED) return previous;
                created[0] = true;
                return new Task(UUID.randomUUID(), Status.PENDING, null);
            });
            return new Submission(task, created[0]);
        }
        boolean compareAndSet(long planId, Task expected, Task updated) {
            return records.replace(planId, expected, updated);
        }
        void clear(long planId) { records.remove(planId); }
        Task get(long planId) { return records.get(planId); }
    }

    static int checks;
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
        System.out.println("PASS " + (++checks) + ": " + label);
    }
    static void rejects(Runnable action, String label) {
        try { action.run(); } catch (InvalidPlan e) { check(true, label); return; }
        throw new AssertionError(label);
    }
    static Plan plan(long category, long project, String name, String amount, String unit) {
        return new Plan(List.of(new Choice(category, project, name, amount, unit)));
    }
    public static void main(String[] args) throws Exception {
        var library = List.of(new Candidate(101, 1001, "Synthetic resource A", Set.of("count")),
                new Candidate(102, 2001, "Synthetic resource B", Set.of("seconds")));
        var valid = plan(101, 1001, "Model-invented name", "10", "count");
        check(validate(valid, library).get(0).name().equals("Synthetic resource A"), "trusted library supplies the name");
        rejects(() -> validate(plan(101, 2001, "B", "10", "seconds"), library), "existing ID in wrong category is rejected");
        rejects(() -> validate(plan(101, 1001, "A", "10", "seconds"), library), "unit mismatch is rejected");
        rejects(() -> validate(plan(101, 1001, "A", "10-15", "count"), library), "range text is not a numeric amount");
        rejects(() -> validate(new Plan(List.of(valid.choices().get(0), valid.choices().get(0))), library), "duplicate item is rejected");
        var calls = new AtomicInteger();
        var repaired = generate(() -> calls.incrementAndGet() == 1
                ? plan(101, 2001, "B", "10", "seconds") : valid, library, 1);
        check(calls.get() == 2 && repaired.size() == 1, "one repair allows exactly two calls");
        var failures = new AtomicInteger();
        rejects(() -> generate(() -> { failures.incrementAndGet(); return plan(101, 2001, "B", "10", "seconds"); }, library, 1), "repair limit is enforced");
        check(failures.get() == 2, "failed generation does not loop indefinitely");
        var transportCalls = new AtomicInteger();
        try { generate(() -> { transportCalls.incrementAndGet(); throw new IllegalStateException("synthetic HTTP failure"); }, library, 1); }
        catch (IllegalStateException e) { /* expected */ }
        check(transportCalls.get() == 1, "transport failure does not enter output repair");
        var store = new TaskStore();
        var first = store.submit(1001);
        check(!store.submit(1001).created(), "same active plan reuses the task");
        check(store.submit(1002).created(), "different plan ID can create another task");
        var a = first.task();
        var runningA = new Task(a.executionId(), Status.RUNNING, null);
        check(store.compareAndSet(1001, a, runningA), "A starts only from its expected snapshot");
        store.clear(1001);
        var b = store.submit(1001).task();
        var completedB = new Task(b.executionId(), Status.SUCCEEDED, "B result");
        check(store.compareAndSet(1001, b, completedB), "B result is stored");
        check(!store.compareAndSet(1001, runningA, new Task(a.executionId(), Status.SUCCEEDED, "A result"))
                && store.get(1001).equals(completedB), "late A cannot overwrite B");
        var concurrent = new TaskStore();
        var start = new CountDownLatch(1);
        var created = new AtomicInteger();
        var pool = Executors.newFixedThreadPool(8);
        var futures = new ArrayList<Future<?>>();
        try {
            for (int i = 0; i < 16; i++) futures.add(pool.submit(() -> {
                try { start.await(); } catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new RuntimeException(e); }
                if (concurrent.submit(99).created()) created.incrementAndGet();
            }));
            start.countDown();
            for (var f : futures) f.get();
        } finally { pool.shutdownNow(); }
        check(created.get() == 1, "16 concurrent submissions create one active task");
        System.out.println("All " + checks + " checks passed. No model, database, or clinical evaluation was performed.");
    }
}
