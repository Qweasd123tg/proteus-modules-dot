def lift(source,base,root,packet):
    d=root/'src';d.mkdir(parents=True,exist_ok=True)
    (d/'backend.rs').write_bytes(source+b'\n#[cfg(test)]\nmod fixture;\n')
    z=d/'backend';z.mkdir(exist_ok=True)
    (z/'fixture.rs').write_bytes((packet/'fixture.rs').read_bytes())
    (d/'meter.rs').write_bytes((packet/'meter.rs').read_bytes())
    # Import the original client-common origin guard and its real URL parser
    # without unrelated Core DTOs or client-common headless modules.
    prefix=base[:base.index('\npub mod pending;')]
    body=base[base.index('\n/// Parses and canonicalizes'):]
    (d/'lib.rs').write_text('#![allow(dead_code)]\nextern crate self as proteus_client_common;\nmod backend;\n#[cfg(test)]mod meter;\n'+prefix+body)
    for n in ('Cargo.toml','Cargo.lock'):
        if (packet/n).exists():
            b=(packet/n).read_bytes().replace(b'backend-diagnostic-m411-proof',f'backend-diagnostic-m411-{root.name}'.encode())
            (root/n).write_bytes(b)
    script=root/'synthetic-backend.py'
    script.write_bytes((packet/'synthetic-backend.py').read_bytes())
    script.chmod(0o755)
