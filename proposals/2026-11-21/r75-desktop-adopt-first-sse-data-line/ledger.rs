use std::cell::Cell;

thread_local! {
    static PEAK_CAPACITY: Cell<usize> = const { Cell::new(0) };
    static COPIED: Cell<usize> = const { Cell::new(0) };
}
pub fn append(data: &mut String, value: &str) {
    COPIED.with(|count| count.set(count.get() + value.len()));
    data.push_str(value);
}
pub fn take() -> usize {
    COPIED.with(|count| count.replace(0))
}

pub fn sample_capacity(data: &String, line: &String) {
    PEAK_CAPACITY.with(|peak| {
        peak.set(
            peak.get()
                .max(data.capacity().saturating_add(line.capacity())),
        )
    });
}
pub fn take_peak() -> usize {
    PEAK_CAPACITY.with(|count| count.replace(0))
}
