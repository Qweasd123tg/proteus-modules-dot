from pathlib import Path

def lift(source,arm,packet,contracts):
    d=arm/'src'
    d.mkdir(parents=True,exist_ok=True)
    for n,v in source.items():
        if n.startswith('src/transcript/'):
            f=arm/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(v)
        if n.startswith('crates/proteus-contracts/'):
            f=contracts/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(v)
    types=source['src/agents/codex/types.rs'].decode()
    start='#[derive(Clone, Debug, PartialEq)]\npub struct Item'
    end='#[derive(Clone, Debug, PartialEq)]\npub enum CatalogEvent'
    a=types.index(start)
    (d/'agents.rs').write_text('pub(crate) mod codex { use serde_json::Value;\n'+types[a:types.index(end,a)]+'}\n')
    (d/'lib.rs').write_text('#![allow(dead_code)]\nmod agents;mod transcript;\n#[cfg(test)]mod fixture;\n#[cfg(test)]mod meter;\n')
    for n in ('fixture.rs','meter.rs'):
        (d/n).write_bytes((packet/n).read_bytes())
    for n in ('Cargo.lock','Cargo.toml'):
        (arm/n).write_bytes((packet/n).read_bytes().replace(b'desktop-capped-request-proof',f'desktop-capped-request-proof-{arm.name}'.encode()))
