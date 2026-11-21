#![allow(dead_code)]
#[cfg(count)]
mod counter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    struct Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static A: Counter = Counter;
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(layout.size(), Relaxed);
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) }
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(new, Relaxed);
            unsafe { System.realloc(p, layout, new) }
        }
    }
    pub fn read() -> (usize, usize) {
        (CALLS.load(Relaxed), BYTES.load(Relaxed))
    }
}
mod tested {
    include!("tested.inc");
    use std::hash::{Hash, Hasher};
    use std::hint::black_box;
    use std::time::Instant;

    fn begin(query: &str) -> Option<Finder> {
        let finder = Finder::new(query);
        (!finder.terms.is_empty()).then_some(finder)
    }

    fn builtin(query: &str) -> Vec<Hit> {
        let Some(mut finder) = begin(query) else {
            return Vec::new();
        };
        include!("rows.inc");
        finder.finish()
    }
    fn mixed(query: &str, large: &str, count: usize) -> Vec<Hit> {
        let Some(mut finder) = begin(query) else {
            return Vec::new();
        };
        for i in 0..count {
            let (title, second, third) = match i % 5 {
                0 => ("Шрифт чата", "Условия текста", ""),
                1 => ("Шрифт чата крупнее", "Текст с пробелом", "АЯ"),
                2 => ("Размер чата: шрифт", "", "Ввод текста"),
                3 => ("Шрифт темы", "чата", "ОС"),
                _ => ("Инструменты", "Без совпадения", "İ"),
            };
            let owned = Hit::new(title, format!("Module {i}"), PageId::Tools)
                .open(vec![format!("params:tool:{i}")])
                .spot(format!("field:{i}"));
            finder.add(owned, &[large, second, third]);
        }
        finder.finish()
    }
    fn brief(mut h: impl Hasher, hits: Vec<Hit>) -> u64 {
        for hit in hits {
            (
                hit.title,
                hit.place,
                hit.target.page,
                hit.target.open,
                hit.target.spot,
            )
                .hash(&mut h);
        }
        h.finish()
    }

    #[test]
    fn real_rows_title_description_and_partial_returns_expected_targets() {
        for (query, title) in [
            ("АВТОПРОКРУТКА", "Автопрокрутка"),
            ("сообщения диалога", "Размер текста"),
            ("РАЗМЕР ввода", "Размер текста"),
            ("Шрифт интерфейса", "Шрифт интерфейса"),
        ] {
            let hits = builtin(query);
            let hit = hits.iter().find(|hit| hit.title == title).unwrap();
            assert_eq!(hit.target.spot, Some(format!("row:{title}")));
            assert!(hit.target.open.is_empty());
        }
        assert_eq!(builtin("Шрифт интерфейса")[0].title, "Шрифт интерфейса");
        assert!(builtin("qxmiss").is_empty());
        assert!(builtin(" \u{2002}\t").is_empty());
    }

    #[test]
    fn json_scope_retargets_only_the_matches_appended_for_this_module() {
        let mut finder = Finder::new("параметр");
        finder.add(
            Hit::new("Параметр старый", "before", PageId::Tools).spot("old".into()),
            &[],
        );
        let first = finder.hits.len();
        let (slot, module, json_mode) = ("model", "fixture", true);
        let open: &[String] = &["params:model:fixture".to_owned()];
        finder.add(
            Hit::new("Параметр", "module", PageId::Models)
                .open(vec!["module:advanced".into()])
                .spot("field:a".into()),
            &[],
        );
        finder.add(
            Hit::new("Строка", "module", PageId::Models)
                .open(vec!["module:group".into()])
                .spot("field:b".into()),
            &["другой параметр"],
        );
        finder.add(Hit::new("Чат", "no", PageId::Chat), &[]);
        include!("json_transform.inc");
        let hits = finder.finish();
        let anchor = spot::params_json(slot, module);
        assert_eq!(hits.len(), 3);
        assert_eq!(hits[1].target.spot.as_deref(), Some("old"));
        for i in [0, 2] {
            let hit = &hits[i];
            assert_eq!(hit.place, "module · JSON");
            assert_eq!(hit.target.open, open);
            assert_eq!(hit.target.spot.as_ref(), Some(&anchor));
        }
    }

    pub fn main() {
        let large = "Description and KEYWORD метка Σος слово документы · λ K
"
        .repeat(32);
        let arm = std::env::args().nth(1).unwrap();
        for (name, query, count) in [
            ("real-title", "АВТОПРОКРУТКА", 0),
            ("real-desc", "сообщения диалога", 0),
            ("real-partial", "РАЗМЕР ввода", 0),
            ("real-miss", "qxmiss", 0),
            ("real-empty", " \t", 0),
            ("stress-title", "шрифт чата", 2048),
            ("stress-miss", "ABSENT", 2048),
        ] {
            let call = || {
                if count == 0 {
                    builtin(black_box(query))
                } else {
                    mixed(black_box(query), black_box(&large), count)
                }
            };
            let digest = brief(std::collections::hash_map::DefaultHasher::new(), call());
            #[cfg(count)]
            {
                let (a, b) = crate::counter::read();
                let hits = call();
                let (c, d) = crate::counter::read();
                black_box(&hits);
                println!("alloc\t{arm}\t{name}\t{digest}\t{}\t{}", c - a, d - b);
            }
            #[cfg(not(count))]
            if name != "real-empty" {
                let batches = if count == 0 { 64 } else { 1 };
                let mut samples = Vec::new();
                for _ in 0..22 {
                    let begin = Instant::now();
                    for _ in 0..batches {
                        black_box(call());
                    }
                    samples.push(begin.elapsed().as_nanos() / batches);
                }
                samples.remove(0);
                samples.sort_unstable();
                println!(
                    "time\t{arm}\t{name}\t{digest}\t{}",
                    samples[samples.len() / 2]
                );
            }
        }
        let mut h = std::collections::hash_map::DefaultHasher::new();
        for query in [
            "σ",
            "Σος",
            "Ι",
            "İ",
            "K",
            "вВОД",
            "метка Σος",
            "не подходит Σ",
            "шрифт",
            "СЛОВО",
            "документы keyword",
        ] {
            for size in [1, 20, 59, 60, 61, 255] {
                h.write_u64(brief(
                    std::collections::hash_map::DefaultHasher::new(),
                    mixed(query, &large, size),
                ));
            }
        }
        println!("parity\t{arm}\t{}", h.finish());
    }
}
fn main() {
    tested::main()
}
