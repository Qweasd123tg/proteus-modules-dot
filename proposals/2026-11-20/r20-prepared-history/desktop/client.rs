// Private bench driver only. All HTTP, timeout, authentication, transport and
// typed decoding below come from unmodified pinned Desktop modules.
#![allow(dead_code)]
#[path="pinned/src/api/mod.rs"] mod api;
#[path="pinned/src/startup_trace.rs"] mod startup_trace;
#[path="pinned/backend_constant.rs"] mod backend;
use anyhow::{Context, Result, ensure};
use proteus_contracts::app_protocol::AppTranscriptCursor;
use serde_json::json;
use std::{env, io::{self, BufRead, Write}, path::{Path,PathBuf}, sync::Arc, thread, time::Instant};

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Query { id: String, dir: PathBuf, before: Option<usize>, revision: Option<String> }

fn invoke(api: &api::Api, dir: &Path, before: Option<usize>, revision: Option<String>) -> serde_json::Value {
    let t = Instant::now();
    let result = match (before, revision) {
        (Some(before), Some(revision)) => api.history_page(dir, &AppTranscriptCursor{before, revision, base: None}),
        (None, None) => api.initial_history_page(dir),
        _ => Err(anyhow::anyhow!("before and revision must be given together")),
    };
    let ms = t.elapsed().as_secs_f64()*1000.;
    match result {
        Ok(page) => json!({"ok":true,"api_ms":ms,"page":page}),
        Err(e) => json!({"ok":false,"api_ms":ms,"error":format!("{e:#}")}),
    }
}

fn main() -> Result<()> {
    let mut a = env::args().skip(1);
    let origin = a.next().context("usage: client <http://127.0.0.1:port> <session_dir | --stdio> [before revision]")?;
    ensure!(proteus_client_common::normalize_local_origin(&origin).is_ok(), "local origin only");
    let client = api::Api::new(&origin, &env::var("PROTEUS_BENCH_TOKEN").unwrap_or_default());
    let mode = a.next().context("missing session_dir or --stdio")?;
    if mode != "--stdio" {
        let before = a.next().map(|s| s.parse()).transpose()?;
        let revision = a.next();
        ensure!(a.next().is_none(), "too many arguments");
        let result = invoke(&client, Path::new(&mode), before, revision);
        println!("{result}");
        if result["ok"] != true { std::process::exit(2); }
    } else {
        let client=Arc::new(client);
        println!("{}",json!({"ready":true}));
        io::stdout().flush()?;
        thread::scope(|s| -> Result<()> {
            for line in io::stdin().lock().lines() {
                let q: Query=serde_json::from_str(&line?)?;
                let client=client.clone();
                s.spawn(move || {
                    let mut r=invoke(&client,&q.dir,q.before,q.revision);
                    r["id"]=json!(q.id);
                    let mut out=io::stdout().lock();
                    writeln!(out,"{r}").expect("stdout");
                    out.flush().expect("flush");
                });
            }
            Ok(())
        })?;
    }
    Ok(())
}
