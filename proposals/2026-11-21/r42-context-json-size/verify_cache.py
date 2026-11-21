"""Run selected existing synchronous Core test bodies with cached dependencies and no full test linker output."""
from pathlib import Path
import os,re,shutil,subprocess as sp,sys,tempfile,tomllib
repo,deps=map(lambda s:Path(s).resolve(),sys.argv[1:])
pkg=repo/'crates/proteus-core'; cfg=tomllib.loads((pkg/'Cargo.toml').read_text())
view=Path('src/core/session_store/remote/view')
groups={view/'tests.rs':['cache_pages_have_a_byte_budget_and_tool_index_repairs_without_journal_scan',
                        'acknowledged_turn_updates_saved_pages_without_reading_the_journal',
                        'remote_display_append_reuses_prefix_pages_and_matches_full_projection'],
        view/'tests/packs.rs':['physical_packs_preserve_logical_leaves_and_skip_the_latest_window',
                              'historical_packs_obey_actual_json_byte_cap_and_large_leaf_remains_readable',
                              'invalid_archive_objects_and_spans_are_cache_misses_not_mixed_rows',
                              'framed_pack_reads_recheck_backing_and_bound_logical_leaf_bytes']}
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)/'crates'/'proteus-core'
    root.mkdir(parents=True)
    # Mirror directories without duplicating file bodies; only write new private files in tmp.
    for p in pkg.rglob('*'):
        dest=root/p.relative_to(pkg)
        if p.is_dir(): dest.mkdir(parents=True,exist_ok=True)
        elif p.is_file(): dest.symlink_to(p)
    def edit(path, old, new):
        p=root/path
        s=p.read_text(); assert old in s,(path,old)
        p.unlink()
        p.write_text(s.replace(old,new,1))
    edit('src/core/mod.rs','mod session_store;', 'pub(crate) mod session_store;')
    edit('src/core/session_store/remote/view.rs','mod tests;', 'pub(crate) mod tests;')
    edit(view/'tests.rs','mod packs;', 'pub(crate) mod packs;')
    calls=[]
    for p,names in groups.items():
        for name in names:
            edit(p,'#[test]\nfn '+name,'pub(crate) fn '+name)
            prefix='core::session_store::remote::view::tests::'+('packs::' if p.stem=='packs' else '')
            calls.append(f'    {prefix}{name}(); println!("ok: {name}");')
    (root/'src/selected.rs').write_text((pkg/'src/lib.rs').read_text()+'\nfn main(){\n'+'\n'.join(calls)+'\n}\n')
    cmd=['rustc','--edition=2024','--crate-name','proteus_core','--cfg','test','--crate-type','bin',
         '-Awarnings','-Cdebuginfo=0','-Cstrip=symbols','-Ccodegen-units=8','-Clink-arg=-fuse-ld=lld','-L',f'dependency={deps}']
    for name in {**cfg['dependencies'],**cfg['target']['cfg(unix)']['dependencies']}:
        name=name.replace('-','_')
        choices=list(deps.glob(f'lib{name}-*.rlib'))+list(deps.glob(f'lib{name}-*.so'))
        assert len(choices)==1,(name,choices)
        cmd.extend(['--extern',f'{name}={choices[0]}'])
    env={**os.environ,'CARGO_MANIFEST_DIR':str(pkg),'CARGO_PKG_VERSION':cfg['package']['version'],'PROTEUS_BUILD_COMMIT':'32e56ecb'}
    sp.run(cmd+['src/selected.rs','-o',str(root/'selected')],cwd=root,env=env,check=True)
    sp.run([root/'selected'],cwd=pkg,env=env,check=True)
