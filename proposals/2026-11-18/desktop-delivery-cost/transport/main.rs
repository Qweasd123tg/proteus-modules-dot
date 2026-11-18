//! Headless consumer for the pinned Desktop transports. No GPUI or frame timing.
#![allow(dead_code)]

use std::{
    io::{self, BufRead},
    path::{Path, PathBuf},
    time::Instant,
};

use anyhow::{Result, ensure};
use serde_json::json;
use sha2::{Digest, Sha256};

mod declarative;
mod preferences;

use declarative::{
    process::{Process, Signal},
    protocol::{self, Content, Incoming, Outgoing, Server, SurfaceKind},
    widget::Node,
};
use proteus_diff as diff;

fn verify(line: &str) -> Result<()> {
    if let Incoming::View { root, .. } = protocol::parse(line)? {
        root.visit(&mut |node| {
            assert!(!matches!(node, Node::Unknown), "unknown shipped widget");
        });
    }
    Ok(())
}

fn wait_for_observer(stage: &str) -> Result<()> {
    println!("{stage}");
    io::stdin().read_line(&mut String::new())?;
    Ok(())
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args[1] == "--wire" {
        let mut n = 0;
        for line in io::stdin().lock().lines() {
            verify(&line?)?;
            n += 1;
        }
        ensure!(n >= 30);
        println!("{n} wire records parsed; all View nodes recognised");
        return Ok(());
    }

    let dir = Path::new(&args[1]).canonicalize()?;
    let (catalog, errors) = declarative::manifest::discover(&dir);
    ensure!(errors.is_empty(), "{errors:?}");
    let extension = catalog
        .iter()
        .find(|entry| entry.manifest.id == "markdown-render")
        .unwrap();
    let (proc, signals) = Process::spawn(extension)?;
    proc.send(&Outgoing::Hello {
        protocol: protocol::PROTOCOL,
        features: protocol::FEATURES.iter().map(|s| s.to_string()).collect(),
        workspace: "/fixture".into(),
        server: Server {
            origin: String::new(),
            token: String::new(),
        },
    })?;

    let source = std::fs::read_to_string(&args[2])?;
    let count: usize = args[3].parse()?;
    let memory = args.get(4).is_some_and(|v| v == "--memory");
    let mut elapsed = Vec::new();
    let mut hashes = Vec::new();
    for i in 0..=count {
        if memory && i == 1 {
            wait_for_observer("READY")?;
        }
        let revision = Some(i as u64);
        let text = if i == 0 {
            "warmup".into()
        } else {
            format!("{} {}", source, (i - 1) % 2)
        };
        let req = Outgoing::Render {
            context: "scope".into(),
            view: "content:0".into(),
            surface: SurfaceKind::Content,
            argument: Some("0".into()),
            session_dir: Some(PathBuf::from("/fixture-session")),
            content: Some(Content {
                language: "text/plain".into(),
                source: text,
                source_revision: revision,
                context: json!({"languages": ["latex"]}),
            }),
        };

        let start = Instant::now();
        proc.send(&req)?;
        let data = futures_lite::future::block_on(signals.recv())?;
        let root = data.with_signal(|sig| match sig {
            Signal::Message(Incoming::View {
                view,
                source_revision,
                root,
                session_dir,
                ..
            }) => {
                assert_eq!(view, "content:0");
                assert_eq!(source_revision, revision);
                assert_eq!(session_dir.as_deref(), Some(Path::new("/fixture-session")));
                root
            }
            other => panic!("{other:?}"),
        });
        let ns = start.elapsed().as_nanos();

        let Node::RichText { html, inlines, .. } = root else {
            panic!("expected rich text");
        };
        assert!(inlines.is_empty());
        if i > 0 {
            elapsed.push(ns);
            hashes.push(format!("{:x}", Sha256::digest(html.as_bytes())));
        }
    }
    if memory {
        wait_for_observer("DONE")?;
    }
    proc.send(&Outgoing::Close {
        view: "content:0".into(),
    })?;
    println!("{}", json!({"ns": elapsed, "html_sha256": hashes}));
    Ok(())
}
