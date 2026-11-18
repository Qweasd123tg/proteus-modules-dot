//! Public SDK content adapter. Never linked into the offline renderer test.
mod tally;
use proteus_extension::{Extension, Host, Result, Surface, anyhow, run};

struct TinyTally;

impl Extension for TinyTally {
    fn render(&mut self, host: &mut Host, view: &str, surface: Surface, _: Option<&str>) -> Result {
        if surface != Surface::Content {
            return Err(anyhow!("expected the content surface"));
        }
        let block = host
            .content(view)
            .ok_or_else(|| anyhow!("missing content"))?;
        if block.language != "tiny-tally" {
            return Err(anyhow!("expected the tiny-tally language"));
        }
        let root = tally::render(&block.source);
        host.show(view, root);
        Ok(())
    }
}

fn main() {
    run(TinyTally);
}
