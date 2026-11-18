//! A single retained assistant reply, no window or GPU. The production queue,
//! source gate, transport and renderer are not reimplemented here.
#![allow(dead_code)]

use std::{path::Path, sync::Arc, time::Instant};

use anyhow::{Result, ensure};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

mod content_queue;
mod declarative;
mod preferences;

use content_queue::ContentQueue;
use declarative::{
    process::{Process, Signal, Signals},
    protocol::{self, Content, Incoming, Outgoing, Server, SurfaceKind},
    widget::Node,
};
use proteus_diff as diff;

include!("updated_content.rs");

const VIEW: &str = "content:reply";
const SESSION: &str = "/fixture-session";

fn send(process: &Process, view: &str, mut content: Content) -> Result<()> {
    content.context["theme"] = json!({"appearance":"dark"});
    process.send(&Outgoing::Render {
        context: "scope".into(),
        view: view.into(),
        surface: SurfaceKind::Content,
        argument: Some("0".into()),
        session_dir: Some(SESSION.into()),
        content: Some(content),
    })
}

fn recv(signals: &Signals, view: &str, revision: Option<u64>) -> Result<Node> {
    futures_lite::future::block_on(signals.recv())?.with_signal(|signal| {
        let Signal::Message(Incoming::View {
            view: reply_view, source_revision, session_dir, root, ..
        }) = signal else {
            anyhow::bail!("unexpected response {signal:?}")
        };
        ensure!(reply_view == view && source_revision == revision);
        ensure!(session_dir.as_deref() == Some(Path::new(SESSION)));
        Ok(root)
    })
}

fn close(process: &Process, view: &str) -> Result<()> {
    process.send(&Outgoing::Close { view: view.into() })
}

fn fresh(process: &Process, signals: &Signals, content: &Content, view: &str) -> Result<Node> {
    send(process, view, content.clone())?;
    let root = recv(signals, view, content.source_revision)?;
    close(process, view)?;
    Ok(root)
}

struct Session<'a> {
    process: &'a Process,
    signals: &'a Signals,
    latest: Option<Arc<Content>>,
    queue: ContentQueue,
    inflight: Option<Arc<Content>>,
    skipped_same: usize,
    revisions: usize,
    offered_bytes: usize,
    submitted_bytes: usize,
    html_bytes: usize,
    accepted: usize,
    stale: usize,
    sent: Vec<u64>,
    proofs: Vec<Value>,
    proof: bool,
}

impl Session<'_> {
    fn render(&mut self) -> Result<()> {
        let latest = self.latest.as_ref().unwrap();
        if let Some(wire) = self.queue.begin_with(latest.source_revision, || latest.as_ref().clone()) {
            assert!(self.inflight.is_none());
            self.submitted_bytes += wire.source.len();
            self.sent.push(wire.source_revision.unwrap());
            self.inflight = Some(latest.clone());
            send(self.process, VIEW, wire)?;
        }
        Ok(())
    }

    fn offer(&mut self, source: &str, context: &Value, invalidate: bool) -> Result<()> {
        self.offered_bytes += source.len();
        let row = match &self.latest {
            None => Arc::new(Content {
                language: "text/markdown".into(),
                source: source.into(),
                context: context.clone(),
                source_revision: Some(0),
            }),
            Some(current) => {
                match updated_content(current, "text/markdown", source, context.clone()) {
                    Some(change) => change,
                    None => {
                        self.skipped_same += 1;
                        // Explicit runtime invalidation; not caused by a redraw/duplicate source.
                        return if invalidate { self.render() } else { Ok(()) };
                    }
                }
            }
        };
        self.revisions += 1;
        self.latest = Some(row);
        self.render()
    }

    fn drain(&mut self) -> Result<Option<Node>> {
        let mut last = None;
        while let Some(sent) = self.inflight.take() {
            let rev = sent.source_revision;
            let root = recv(self.signals, VIEW, rev)?;
            let current = self.latest.as_ref().unwrap().source_revision;
            if rev == current { self.accepted += 1; } else { self.stale += 1; }
            let Node::Stack { children, .. } = &root else {
                anyhow::bail!("expected Markdown body");
            };
            let [Node::RichText { html, inlines, .. }] = children.as_slice() else {
                anyhow::bail!("expected one prose surface");
            };
            ensure!(inlines.is_empty(), "fixtures contain no slots");
            self.html_bytes += html.len();
            if self.proof {
                // Outside the timing runs, re-render every admitted prefix in a new view
                // and compare the entire validated node tree, not just the text.
                let oracle = fresh(self.process, self.signals, &sent, "oracle")?;
                ensure!(root == oracle, "retained output differs from fresh at {rev:?}");
                self.proofs.push(json!({
                    "rev":rev, "source_bytes":sent.source.len(),
                    "tree_sha256":digest(&format!("{root:?}")),
                    "html_sha256":digest(html), "html_bytes":html.len(),
                    "first_html":html.lines().next().unwrap_or_default().chars().take(140).collect::<String>(),
                }));
            }
            if rev == current { last = Some(root); }
            if self.queue.finish(rev, current) { self.render()?; }
        }
        Ok(last)
    }
}

fn digest(data: &str) -> String {
    format!("{:x}", Sha256::digest(data.as_bytes()))
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    ensure!(args.len() >= 6, "usage: PACKAGES FILE N GROUP grow|same|invalidation [--proof]");
    let packages = Path::new(&args[1]).canonicalize()?;
    let source = std::fs::read_to_string(&args[2])?;
    let count: usize = args[3].parse()?;
    let group: usize = args[4].parse()?;
    ensure!(count > 0 && count <= source.len() && group > 0);
    let mode = &args[5];
    ensure!(matches!(mode.as_str(), "grow" | "same" | "invalidation"));
    let proof = args.get(6).is_some_and(|x| x == "--proof");

    let (catalog, errors) = declarative::manifest::discover(&packages);
    ensure!(errors.is_empty(), "{errors:?}");
    let extension = catalog.iter().find(|e| e.manifest.id == "markdown-render").unwrap();
    let (process, signals) = Process::spawn(extension)?;
    process.send(&Outgoing::Hello {
        protocol: protocol::PROTOCOL,
        features: protocol::FEATURES.iter().map(|s| s.to_string()).collect(),
        workspace: "/fixture".into(),
        server: Server { origin: String::new(), token: String::new() },
    })?;
    let context = json!({
        "languages":["json-render","svg","md","markdown","mermaid"],
        "contributors":{"json-render":"json-render","svg":"json-render","md":"markdown-render",
                        "markdown":"markdown-render","mermaid":"mermaid-render"},
    });
    let _ = fresh(&process, &signals, &Content {
        language: "text/markdown".into(), source: "warmup".into(),
        context: context.clone(), source_revision: Some(0),
    }, "warmup")?;
    let mut session = Session {
        process: &process, signals: &signals, latest: None, queue: ContentQueue::default(),
        inflight: None, skipped_same: 0, revisions: 0, submitted_bytes: 0, offered_bytes: 0,
        html_bytes: 0, accepted: 0, stale: 0, sent: Vec::new(), proofs: Vec::new(), proof,
    };
    let mut final_root = None;
    let start = Instant::now();
    for i in 1..=count {
        let end = if mode == "grow" {
            source.floor_char_boundary(source.len() * i / count)
        } else {
            source.len()
        };
        session.offer(&source[..end], &context, mode == "invalidation")?;
        if i % group == 0 || i == count {
            if let Some(root) = session.drain()? { final_root = Some(root); }
        }
    }
    let elapsed_ns = start.elapsed().as_nanos();
    let final_root = final_root.unwrap();
    ensure!(session.latest.as_ref().unwrap().source == source);
    close(&process, VIEW)?;
    println!("{}", json!({
        "count":count, "group":group, "mode":mode,
        "source_sha256":digest(&source), "final_sha256":digest(&format!("{final_root:?}")),
        "offers":count, "revisions":session.revisions, "unchanged_offers":session.skipped_same,
        "sent_revisions":session.sent, "accepted":session.accepted, "stale":session.stale,
        "offered_bytes":session.offered_bytes, "submitted_source_bytes":session.submitted_bytes,
        "returned_html_bytes":session.html_bytes, "proofs":session.proofs,
        "elapsed_ns":if proof {None} else {Some(elapsed_ns)},
    }));
    Ok(())
}
