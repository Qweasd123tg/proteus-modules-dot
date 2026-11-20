use std::{
    fs,
    hint::black_box,
    path::{Component, Path, PathBuf},
    time::Instant,
};

struct SearchQuery {
    starts_with: Vec<String>,
    cwd: PathBuf,
}

fn main() {
    let dir = PathBuf::from(std::env::args_os().nth(1).unwrap());
    fs::create_dir_all(&dir).unwrap();
    let paths = [
        "a",
        "a/b",
        "a/b/c",
        "a/d",
        "a!",
        "a!/x",
        "aa",
        "aa/b",
        "d",
        "résumé",
        "résumé/y",
    ];
    for p in paths {
        fs::create_dir_all(dir.join(p)).unwrap();
    }
    // Include lexical normalization, rejected roots, file-prefix and missing-dir fallbacks.
    let terms = [
        "./a/",
        "a/b/",
        "a/b/c/",
        "a//d/",
        "a!/",
        "a!/x/",
        "aa/",
        "aa/b/",
        "d/",
        "résumé/y/",
        "absent/sub/",
        ".",
        "a/b/./c/",
        "a/does-not-exist/file",
        "file",
        "/tmp",
        "../outside",
    ];
    let mut cases = 0;
    for mask in 0..1 << 11 {
        let base: Vec<_> = terms[..11]
            .iter()
            .enumerate()
            .filter(|(i, _)| (1 << i) & mask != 0)
            .map(|(_, p)| p.to_string())
            .collect();
        for extra in [
            None,
            Some(terms[11]),
            Some(terms[12]),
            Some(terms[13]),
            Some(terms[14]),
            Some(terms[15]),
            Some(terms[16]),
        ] {
            let mut terms = base.clone();
            terms.reverse();
            if let Some(p) = extra {
                terms.push(p.to_string());
                terms.push(p.to_string());
            }
            let query = SearchQuery {
                starts_with: terms,
                cwd: dir.clone(),
            };
            let a = stock::search_roots(&query);
            let b = candidate::search_roots(&query);
            // Compare emitted OS argument text, not merely normalized Path equality.
            assert!(
                a.len() == b.len()
                    && a.iter()
                        .zip(&b)
                        .all(|(a, b)| a.as_os_str() == b.as_os_str()),
                "{:?} -> {:?} != {:?}",
                query.starts_with,
                a,
                b
            );
            cases += 1;
        }
    }
    println!("exact differential root sets: {cases}");
    println!("shape,root_count,round,iterations,stock_ns_each,candidate_ns_each");
    let all: Vec<_> = (0..2048).map(|i| format!("branch-{i:04}/")).collect();
    for name in &all {
        fs::create_dir(dir.join(name)).unwrap();
    }
    for (n, iterations) in [
        (0, 1500),
        (1, 1000),
        (16, 80),
        (128, 12),
        (512, 2),
        (2048, 1),
    ] {
        let q = SearchQuery {
            starts_with: all[..n].iter().rev().cloned().collect(),
            cwd: dir.clone(),
        };
        for r in 0..7 {
            let mut times = [0; 2];
            let funcs: [fn(&SearchQuery) -> Vec<PathBuf>; 2] =
                [stock::search_roots, candidate::search_roots];
            for j in 0..2 {
                let j = (j + r) % 2;
                let start = Instant::now();
                for _ in 0..iterations {
                    black_box(funcs[j](black_box(&q)));
                }
                times[j] = start.elapsed().as_nanos() / iterations;
            }
            println!("siblings,{n},{r},{iterations},{},{}", times[0], times[1]);
        }
    }
}
