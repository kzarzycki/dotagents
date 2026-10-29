import contextlib
import hashlib
import http.server
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'home/.local/bin/disk-hygiene'

# The repo is public, so the names that must not appear in the script or its docs are kept as hashes.
# ponytail: a hash only hides a short name from text search, a guess recovers it; a list kept outside the repo
# would hide it fully but CI could not run the check.
PRIVATE_HASHES = {
    '59ce113c13ade62d5645165fee8b1a5ab8ec124a9a735033f2d4b255b95c9015',
    'd999056550fd648de6de0537f389c3da467f846a4fd6117a62cb54ba1c23cf3c',
    '4046498b2dc5b9e89212ab8c64a866a8720ee806fdd7ada31dcba89f1422fb1e',
    '8be0b5445fca6eb16d14c6f4eaff1cf1d1a3362ef660bfb2b66e74bf309b7e61',
    'baa30c0f11fd0cf29d3eac75986fbe7803b0458e96676945920c2fe7fb84d59f',
    '0dac47612d8c0bd98d536e3c69d8b87071986524f4b4e17fa44cf680bdf1ef67',
}


def load(name, path=SCRIPT):
    """The extensionless script as a module, with HOME as the test set it."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    sys.dont_write_bytecode, saved = True, sys.dont_write_bytecode  # a cache in home/ would be linked by install
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    return module


def private_words(text):
    """The hashed names in text: any word, or run of words joined by hyphens."""
    runs = re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)*', text.lower())
    words = {w for r in runs for w in (r, *r.split('-'))}
    return sorted(w for w in words if hashlib.sha256(w.encode()).hexdigest() in PRIVATE_HASHES)


def test_private_words_finds_a_hashed_word(monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], 'PRIVATE_HASHES', {hashlib.sha256(b'example').hexdigest()})
    assert private_words('ssh to Example-host.local') == ['example']
    assert private_words('nothing here') == []


def test_names_no_host_or_user():
    for path in (SCRIPT, ROOT / 'README.md'):
        text = path.read_text()
        if path.name == 'README.md':  # only the hygiene section is this script's
            start = text.index('### Disk hygiene')
            text = text[start:text.find('\n#', start + 5)]
        assert not private_words(text), (path, private_words(text))
        assert not re.search(r'/Users/\w|/home/\w', text), path


def test_paths_derive_from_the_linked_checkout(tmp_path):
    link = tmp_path / 'disk-hygiene'
    link.symlink_to(SCRIPT)
    hygiene = load('disk_hygiene_link', link)
    assert hygiene.REPO == ROOT and (ROOT / hygiene.SELF).samefile(SCRIPT)
    assert hygiene.DOTAGENTS == ROOT / 'bin/dotagents'


def test_install_links_script(tmp_path):
    from test_install_subsets import make_checkout, run_install
    repo, home = make_checkout(tmp_path)
    (repo / 'home/.local/bin/__pycache__').mkdir(exist_ok=True)
    (repo / 'home/.local/bin/__pycache__/x.pyc').touch()
    assert run_install(repo, home).returncode == 0
    assert not (home / '.local/bin/__pycache__').exists()
    link = home / '.local/bin/disk-hygiene'
    assert link.is_symlink() and os.access(link, os.X_OK)
    assert subprocess.run([str(link), '--help'], capture_output=True, env={**os.environ, 'HOME': str(home)}).returncode == 0


def test_disk_hygiene(tmp_path, monkeypatch):
    """disk-hygiene against a temporary home: real git checkouts, fake tools, lsof, ps and gh."""
    home = tmp_path.resolve()
    dev, bin_ = home / 'dev', home / 'fakebin'
    bin_.mkdir()
    (home / 'simulators.json').write_text('{"devices": {"iOS-17-0": [{"name": "iPhone 15"}, {"name": "iPad"}]}}')
    for name, body in {'uv': 'echo pruned', 'npm': 'true', 'pre-commit': 'true',
                       'xcrun': f'echo "$@" >> {home}/xcrun.calls; cat {home}/simulators.json',
                       'pnpm': 'echo pruned', 'go': 'sleep 10', 'brew': f'echo {home}/homebrew',
                       'docker': f'echo "$@" >> {home}/docker.calls',
                       'lsof': f'cat {home}/lsof.txt', 'ps': f'cat {home}/ps.txt',
                       'gh': f'exec python3 {home}/gh.py "$@"'}.items():
        (bin_ / name).write_text(f'#!/bin/sh\n{body}\n')
        (bin_ / name).chmod(0o755)
    merged = {}  # branch -> the merged PR's head commit
    (home / 'gh.py').write_text('import json, sys\n'
        f'if sys.argv[1] == "api":  # repos/o/r/commits/<sha>/pulls\n'
        f'    print(json.dumps(json.load(open("{home}/gh-pulls.json")).get(sys.argv[2].split("/")[4], [])))\n'
        '    sys.exit()\n'
        'head = sys.argv[sys.argv.index("--head") + 1]\n'
        f'heads = json.load(open("{home}/gh.json"))\n'
        'print(json.dumps([{"number": 7, "headRefOid": heads[head]}] if head in heads else []))\n')
    old = time.time() - 30 * 86400
    env = {**os.environ, 'HOME': str(home), 'GIT_AUTHOR_DATE': f'@{int(old)}', 'GIT_COMMITTER_DATE': f'@{int(old)}',
           'GIT_CONFIG_GLOBAL': str(home / '.gitconfig'), 'PATH': f'{bin_}:{os.environ["PATH"]}'}
    git = lambda cwd, *a: subprocess.run(['git', '-C', str(cwd), *a], env=env, check=True, text=True,
                                          capture_output=True).stdout.strip()
    (home / '.gitconfig').write_text(f'[user]\nname = t\nemail = t@t\n[url "{home}/origin.git"]\n'
                                     '\tinsteadOf = https://github.com/o/r.git\n')
    git(home, 'init', '-q', '--bare', 'origin.git')
    repo = dev / 'r'
    repo.mkdir(parents=True)
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'remote', 'add', 'origin', 'https://github.com/o/r.git')
    (repo / '.gitignore').write_text('node_modules/\n.env\n.worktrees/\n.coverage\nbuild/\ntmp\n*.log\n*.pyc\n'
                                     '.agents/skills/\n.claude/skills/\ncache/\n.build/\n*.xcodeproj/\n.bootstrap-state/\nfake/\n'
                                     '_build_info.py\ngen_*.py\n.claude/settings.local.json\n.terraform/\n'
                                     'test-results/\nplaywright-report/\nsnapshot_failures/\n**/static/web-ui/\nweb-ui/*.local\nmystatic/web-ui/\n.cfg/\n')
    (repo / '.git/info/exclude').write_text('private/\n*.key\n')  # read like .gitignore
    git(repo, 'add', '.')
    git(repo, 'commit', '-q', '-m', 'base')
    git(repo, 'push', '-q', 'origin', 'main')
    for branch in ('merged', 'dirty', 'unpushed', 'squashed', 'busy', 'open', 'secret', 'private', 'fresh', 'apm',
                   'apm-mine', 'apm-bad', 'locks', 'held', 'many', 'deep-tmp', 'rebuilds', 'xcode', 'bootstrap',
                   'lockdir', 'lockmix', 'generated', 'notgen', 'testout', 'webui', 'webuisrc', 'copy', 'copydiff', 'mystatic', 'copydir'):
        git(repo, 'worktree', 'add', '-q', '-b', branch, str(dev / f'wt-{branch}'))
        wt = dev / f'wt-{branch}'
        (wt / f'{branch}.txt').write_text(branch)
        if branch == 'rebuilds':
            (wt / 'project.yml').write_text('name: App\n')  # XcodeGen rebuilds App.xcodeproj from it
        if branch == 'webuisrc':  # a tracked web-ui/ source dir, with a local ignored file in it
            (wt / 'web-ui').mkdir()
            (wt / 'web-ui/app.js').write_text('source')
        if branch.startswith('apm'):  # what `apm install` deployed, as its lockfile lists it
            (wt / 'apm.lock.yaml').write_text('dependencies:\n- repo_url: o/skills\n  deployed_files:\n'
                '  - .agents/skills/a\n  - .agents/skills/a/SKILL.md\n  - .claude/skills/a\n'
                'local_deployed_files:\n- .claude/skills/local/SKILL.md\n'
                + ('  - .claude/skills/mine\n' if branch == 'apm-bad' else ''))  # YAML: a continuation, no item
        git(wt, 'add', '.')
        git(wt, 'commit', '-q', '-m', branch)
        if branch in ('merged', 'dirty', 'busy', 'secret', 'private', 'fresh', 'apm', 'apm-mine', 'apm-bad', 'locks', 'held',
                      'many', 'deep-tmp', 'rebuilds', 'xcode', 'bootstrap', 'lockdir', 'lockmix', 'generated', 'notgen',
                      'testout', 'webui', 'webuisrc', 'copy', 'copydiff', 'mystatic', 'copydir'):
            git(wt, 'push', '-q', 'origin', branch)
        merged[branch] = git(wt, 'rev-parse', 'HEAD')
    for name in ('test-results', 'playwright-report', 'snapshot_failures'):  # test output goes with the worktree
        (dev / f'wt-testout/{name}').mkdir()
        (dev / f'wt-testout/{name}/x').write_text('')
    (dev / 'wt-webui/pkg/static/web-ui').mkdir(parents=True)  # a built web UI: a path suffix
    (dev / 'wt-webui/pkg/static/web-ui/index.html').write_text('built')
    (dev / 'wt-webuisrc/web-ui/notes.local').write_text('mine')  # not under static/: kept
    (repo / '.env').write_text('TOKEN=shared')  # the main checkout's ignored file; a byte-identical copy goes
    (dev / 'wt-copy/.env').write_text('TOKEN=shared')
    (dev / 'wt-copydiff/.env').write_text('TOKEN=edited')
    (dev / 'wt-mystatic/mystatic/web-ui').mkdir(parents=True)  # not static/web-ui: a different directory name
    (dev / 'wt-mystatic/mystatic/web-ui/notes').write_text('mine')
    (repo / '.cfg').mkdir()  # an ignored directory folded into one entry: every file in it must match
    (repo / '.cfg/a').write_text('shared')
    (dev / 'wt-copydir/.cfg').mkdir()
    (dev / 'wt-copydir/.cfg/a').write_text('shared')
    (dev / 'wt-dirty/untracked').write_text('work in progress')
    (dev / 'wt-busy/untracked').write_text('work in progress')  # in use: kept, and no question
    (dev / 'wt-private/tmp').write_text('private')  # an ignored file named tmp is not a tmp/ directory
    # Ignored files: build output goes with its worktree; a .env or a nested worktree keeps it.
    (dev / 'wt-squashed/node_modules/x').mkdir(parents=True)
    (dev / 'wt-squashed/.coverage').write_text('')
    (dev / 'wt-squashed/tmp/loop').mkdir(parents=True)  # a merged PR's evidence and logs go with it
    (dev / 'wt-squashed/tmp/loop/report.md').write_text('proof')
    (dev / 'wt-squashed/run.log').write_text('log')
    (dev / 'wt-squashed/pkg').mkdir()  # all ignored, but not as a directory: judged file by file
    (dev / 'wt-squashed/pkg/mod.pyc').write_text('')
    for path in [*(dev / 'wt-squashed/tmp').rglob('*'), dev / 'wt-squashed/tmp']:
        os.utime(path, (old, old))  # a day-old tmp/ goes
    (dev / 'wt-fresh/tmp/loop').mkdir(parents=True)  # a lead may still read today's report
    (dev / 'wt-fresh/tmp/loop/report.md').write_text('proof')
    for name in ('apm', 'apm-mine', 'apm-bad'):
        for skill in ('.agents/skills/a/SKILL.md', '.agents/skills/a/agents/openai.yaml',
                      '.claude/skills/a/SKILL.md', '.claude/skills/local/SKILL.md'):
            (dev / f'wt-{name}' / skill).parent.mkdir(parents=True, exist_ok=True)
            (dev / f'wt-{name}' / skill).write_text('skill')
    (dev / 'wt-apm-mine/.claude/skills/mine').mkdir()  # hand-written, not apm's to rebuild
    (dev / 'wt-apm-mine/.claude/skills/mine/SKILL.md').write_text('mine')
    (dev / 'wt-apm-bad/.claude/skills/mine').mkdir()
    (dev / 'wt-apm-bad/.claude/skills/mine/SKILL.md').write_text('mine')
    for name in ('rebuilds', 'xcode', 'bootstrap'):
        (dev / f'wt-{name}/App.xcodeproj').mkdir()
        (dev / f'wt-{name}/App.xcodeproj/project.pbxproj').write_text('{}')
        (dev / f'wt-{name}/.bootstrap-state').mkdir()
        (dev / f'wt-{name}/.bootstrap-state/primary-report.json').write_text('[]')
    (dev / 'wt-bootstrap/project.yml').write_text('name: App\n')  # untracked here: dirty, but names the report too
    (dev / 'wt-xcode/project.yml').write_text('name: Other\n')  # generates Other.xcodeproj, not App's
    (dev / 'wt-xcode/fake').mkdir()  # a file named CACHEDIR.TAG without the signature marks no cache
    (dev / 'wt-xcode/fake/CACHEDIR.TAG').write_text('not a cache tag')
    (dev / 'wt-rebuilds/cache').mkdir()  # tagged as a cache by the Cache Directory Tagging spec
    (dev / 'wt-rebuilds/cache/CACHEDIR.TAG').write_text('Signature: 8a477f597d28d172789f06886806bc55\n')
    (dev / 'wt-rebuilds/cache/blob').write_text('')
    (dev / 'wt-rebuilds/.build/debug').mkdir(parents=True)  # SwiftPM
    for name in ('rebuilds', 'xcode'):
        for path in [*(dev / f'wt-{name}/.bootstrap-state').rglob('*'), dev / f'wt-{name}/.bootstrap-state']:
            os.utime(path, (old, old))
    (dev / 'wt-deep-tmp/build/tmp/loop').mkdir(parents=True)  # status folds it into `!! build/`
    (dev / 'wt-deep-tmp/build/tmp/loop/report.md').write_text('proof')
    (dev / 'wt-locks/empty.lock').write_text('')
    (dev / 'wt-locks/stale.lock').write_text('4242')  # no process holds it
    (dev / 'wt-held/held.lock').write_text('4242')
    for name in ('lockdir', 'lockmix'):  # status folds an untracked directory into `?? locks/`
        (dev / f'wt-{name}/locks').mkdir()
        (dev / f'wt-{name}/locks/stale.lock').write_text('4242')
    (dev / 'wt-lockmix/locks/notes.txt').write_text('mine')
    (dev / 'wt-generated/pkg').mkdir()  # a build writes it, and says so on its first line
    (dev / 'wt-generated/pkg/_build_info.py').write_text('"""Auto-generated at wheel build time; do not edit.\n"""\n')
    # Not marked generated: the marker on a later line, half a marker, a symlink to a marked file.
    (dev / 'wt-notgen/gen_later.py').write_text('# helper\n# Auto-generated; do not edit.\n')
    (dev / 'wt-notgen/gen_half.py').write_text('# Generated once by hand; edit freely.\n')
    (home / 'marked.py').write_text('# Code generated by a tool. DO NOT EDIT.\n')
    (dev / 'wt-notgen/gen_link.py').symlink_to(home / 'marked.py')
    (dev / 'wt-many/notes.txt').write_text('mine')
    (dev / 'wt-many/.env').write_text('TOKEN=local only')
    (dev / 'wt-many/private').mkdir()
    (dev / 'wt-many/private/diary.md').write_text('mine')
    (dev / 'wt-many/id.key').write_text('mine')
    (dev / 'wt-secret/.env').write_text('TOKEN=local only')
    git(repo, 'worktree', 'add', '-q', '-b', 'inner', str(dev / 'wt-secret/.worktrees/inner'), 'merged')
    (dev / 'wt-secret/.worktrees/inner/untracked').write_text('work in progress')
    merged['inner'] = merged['merged']
    # A dirty checkout under an ignored build/: status shows only `!! build/`, which rebuilds.
    git(repo, 'worktree', 'add', '-q', '-b', 'deep', str(dev / 'wt-merged/build/deep'), 'merged')
    (dev / 'wt-merged/build/deep/untracked').write_text('work in progress')
    merged['deep'] = merged['merged']
    # A cloud worker's environment pin and a module's .terraform/ rebuild; a pin with grants may not.
    for name, settings in (('pin', {'remote': {'defaultEnvironmentId': 'env_1'}}),
                           ('grants', {'remote': {'defaultEnvironmentId': 'env_1'}, 'permissions': {'allow': ['Bash(ls)']}})):
        git(repo, 'worktree', 'add', '-q', '-b', name, str(dev / f'wt-{name}'), 'main')
        (dev / f'wt-{name}/.claude').mkdir()
        (dev / f'wt-{name}/.claude/settings.local.json').write_text(json.dumps(settings))
        merged[name] = git(repo, 'rev-parse', 'main')
    (dev / 'wt-pin/stack/.terraform/providers').mkdir(parents=True)
    (dev / 'wt-pin/stack/.terraform/providers/link').write_text('')
    # SwiftPM's dependency clones rebuild; a clone anywhere else, even near a .build/, keeps its worktree.
    swift = {'swift-build': 'pkg/build/dep', 'swift-dotbuild': 'pkg/.build/dep', 'swift-foo': 'pkg/foo.build/checkouts/dep'}
    for name in swift:
        git(repo, 'worktree', 'add', '-q', '-b', name, str(dev / f'wt-{name}'), 'main')
        merged[name] = git(repo, 'rev-parse', 'main')
    for clone in ('wt-pin/pkg/.build/checkouts/dep', 'wt-pin/pkg/.build/checkouts/dep/.build/checkouts/inner',
                  *(f'wt-{name}/{path}' for name, path in swift.items())):
        (dev / clone).mkdir(parents=True)
        git(dev / clone, 'init', '-q')
    # A worker's or agent's worktree with no PR of its own, inside a merged one: judged with it.
    # wt-nest's branch was deleted on merge, so its worker's commit is on no remote, only in the PR head.
    for outer, inner in (('nest', 'agent'), ('hold', 'wip'), ('locked', 'session')):
        wt = dev / f'wt-{outer}'
        git(repo, 'worktree', 'add', '-q', '-b', outer, str(wt), 'main')
        for step in ('worker', 'lead'):  # real changes: an empty commit would pass on its tree alone
            (wt / f'{outer}-{step}.txt').write_text(step)
            git(wt, 'add', '.')
            git(wt, 'commit', '-q', '-m', step)
            if step == 'worker':
                git(repo, 'worktree', 'add', '-q', '-b', inner, str(wt / '.worktrees' / inner), outer)
        merged[outer] = git(wt, 'rev-parse', 'HEAD')
    git(dev / 'wt-hold', 'push', '-q', 'origin', 'hold')
    (dev / 'wt-hold/.worktrees/wip/untracked').write_text('work in progress')
    git(repo, 'worktree', 'lock', str(dev / 'wt-locked/.worktrees/session'))  # no reason: a bare `locked` line
    merged['unpushed'] = git(repo, 'rev-parse', 'main')
    # Squashed on merge: the PR's head is another commit with the same tree, here only locally.
    merged['squashed'] = git(repo, 'commit-tree', 'squashed^{tree}', '-p', 'main', '-m', 'squash')
    del merged['open']
    (home / 'gh.json').write_text(json.dumps(merged))
    pulls = {}  # commit -> the PRs GitHub lists for it, as `gh api repos/o/r/commits/<sha>/pulls` returns them
    for name, state in (('prmerged', 'closed'), ('propen', 'open'), ('prnone', None), ('prearly', 'closed')):  # detached at a PR's head, or at no PR's
        git(repo, 'worktree', 'add', '-q', '--detach', str(dev / f'wt-{name}'), 'main')
        (dev / f'wt-{name}' / f'{name}.txt').write_text(name)
        git(dev / f'wt-{name}', 'add', '.')
        git(dev / f'wt-{name}', 'commit', '-q', '-m', name)  # on no remote branch, as a squash-merged PR's head is
        sha = git(dev / f'wt-{name}', 'rev-parse', 'HEAD')
        if state:  # GitHub lists a PR for each of its commits: prearly is in a closed PR whose head is a later commit
            pulls[sha] = [{'number': 9, 'state': state, 'head': {'sha': '0' * 40 if name == 'prearly' else sha}}]
    (home / 'gh-pulls.json').write_text(json.dumps(pulls))
    (home / 'shared-venv/lib').mkdir(parents=True)
    for name, idle in (('idle', True), ('recent', False), ('busy-env', True), ('linked', True)):
        checkout = dev / name
        if name == 'linked':  # a .venv symlinked elsewhere is not this checkout's to delete
            checkout.mkdir()
            (checkout / '.venv').symlink_to(home / 'shared-venv')
        else:
            (checkout / '.venv/lib').mkdir(parents=True)
        (checkout / 'pyproject.toml').write_text('[project]\n')
        (checkout / '.gitignore').write_text('.venv\nnode_modules/\n')
        git(checkout, 'init', '-q')
        git(checkout, 'add', '.')
        git(checkout, 'commit', '-q', '-m', 'init')
        (checkout / 'node_modules').mkdir()  # no package.json beside it: kept
        if idle:
            for path in [checkout / 'pyproject.toml', checkout / '.gitignore', checkout / '.git/index']:
                os.utime(path, (old, old))
    (dev / 'not-a-checkout/.venv').mkdir(parents=True)
    (dev / 'not-a-checkout/pyproject.toml').write_text('')
    (home / 'lsof.txt').write_text(f'p1\nfcwd\nn{dev}/wt-busy\np2\nf3\nn{dev}/wt-held/held.lock\n')
    (home / 'ps.txt').write_text(f'node /opt/homebrew/bin/pnpm install\npython -m http.server -d {dev}/busy-env\n')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('PATH', env['PATH'])
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', env['GIT_CONFIG_GLOBAL'])
    disk_hygiene_runs(home, dev, repo, git, monkeypatch)


def disk_hygiene_runs(home, dev, repo, git, monkeypatch):
    hygiene = load('disk_hygiene')
    hygiene.REPO, hygiene.DOTAGENTS = home / 'no-checkout', home / 'no-doctor'  # the real ones would fetch and run
    hygiene.CACHES = [(n, c, 1 if n == 'go' else t, b) for n, c, t, b in hygiene.CACHES]
    told = []
    hygiene.tell = lambda text: told.append(text) or 'cos-session'
    pin = {'remote': {'defaultEnvironmentId': 'env_1'}}
    for text, wanted in ((json.dumps(pin), True), (json.dumps(pin) + ' ' * 5000, False),
                         (json.dumps({'remote': {**pin['remote'], 'x': 1}}), False), ('{"remote": ["defaultEnvironmentId"]}', False),
                         ('{"remote": ', False), ('', False)):
        (home / 'settings.json').write_text(text)  # only the pin and nothing else may go
        assert hygiene.pin_only(home / 'settings.json') is wanted, (text[:60], wanted)
    checkout = home / 'apm-checkout'  # a repo that ignores all of .claude/: not_payload() expands `!! .claude/`
    (checkout / '.claude/skills/a').mkdir(parents=True)
    (checkout / '.claude/skills/a/SKILL.md').write_text('skill')
    for settings, wanted in ((pin, []), ({**pin, 'permissions': {}}, ['.claude/settings.local.json'])):
        (checkout / '.claude/settings.local.json').write_text(json.dumps(settings))
        assert hygiene.not_payload(checkout, '.claude/', {'.claude/skills/a'}) == wanted, settings

    def run(*args):
        monkeypatch.setattr(sys, 'argv', ['disk-hygiene', '--dev', str(dev), *args])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = hygiene.main()
        return code, out.getvalue()

    kept = [dev / p for p in ('wt-swift-build', 'wt-swift-dotbuild', 'wt-swift-foo', 'wt-fresh/tmp/loop/report.md', 'wt-apm-mine/.claude/skills/mine/SKILL.md', 'wt-held/held.lock',
                              'wt-apm-bad/.claude/skills/mine/SKILL.md', 'wt-deep-tmp/build/tmp/loop/report.md',
                              'wt-xcode/App.xcodeproj', 'wt-xcode/fake/CACHEDIR.TAG', 'wt-bootstrap/.bootstrap-state',
                              'wt-many/private/diary.md', 'wt-webuisrc/web-ui/notes.local', 'wt-mystatic', 'wt-copydiff/.env', 'wt-lockmix/locks/notes.txt', 'wt-notgen/gen_later.py', 'wt-merged/build/deep/untracked', 'wt-hold/.worktrees/wip/untracked', 'wt-grants/.claude/settings.local.json', 'wt-locked/.worktrees/session', 'wt-secret/.env', 'wt-private/tmp', 'wt-secret/.worktrees/inner/untracked', 'wt-dirty', 'wt-unpushed', 'wt-busy', 'wt-open', 'wt-propen', 'wt-prnone', 'wt-prearly', 'recent/.venv', 'busy-env/.venv',
                              'idle/node_modules', 'not-a-checkout/.venv', 'linked/.venv', '../shared-venv/lib')]
    removed = [dev / p for p in ('wt-prmerged', 'wt-pin', 'wt-nest/.worktrees/agent', 'wt-nest', 'wt-squashed', 'wt-apm', 'wt-locks', 'wt-lockdir', 'wt-generated', 'wt-rebuilds', 'wt-testout', 'wt-webui', 'wt-copy', 'wt-copydir', 'idle/.venv')]
    code, out = run('--dry-run', '--floor-gb', '0')
    assert code == 0 and all(p.exists() for p in kept + removed), out
    assert f'would remove worktree {dev}/wt-squashed' in out and f'would remove env {dev}/idle/.venv' in out, out
    assert 'would tell the chief of staff' in out and not told, out
    assert 'terminals: 0 dead of 0;' in out, out  # main() runs the terminals step
    (home / 'lsof.txt').rename(home / 'lsof.saved')  # the fake lsof fails: nothing may go
    code, out = run('--floor-gb', '0')
    assert code == 1 and 'FAIL process scan' in out and all(p.exists() for p in kept + removed), out
    assert len(told) == 1 and '2 simulator devices whose runtime is gone' in told[0], told
    (home / 'lsof.saved').rename(home / 'lsof.txt')
    code, out = run('--floor-gb', '0')
    assert code == 0, out
    assert all(p.exists() for p in kept), out
    for name in ('swift-build', 'swift-dotbuild', 'swift-foo'):
        line = next(line for line in out.splitlines() if line.startswith(f'skip worktree {dev}/wt-{name} '))
        assert line.endswith('another checkout is inside it') or 'another checkout is inside it;' in line, line
    assert not any(p.exists() for p in removed), out
    assert git(repo, 'rev-parse', 'merged') and git(repo, 'rev-parse', 'agent'), 'the local branches are kept'
    assert 'info\nbuilder prune -f --filter until=24h\n' in (home / 'docker.calls').read_text()
    for line in ('uv: uv cache prune: freed', 'docker: docker builder prune -f --filter until=24h: freed', 'skip pnpm: a pnpm process is running', 'skip go: still running',
                 'skip brew: this account does not own', f'skip worktree {dev}/wt-dirty (o/r#7 merged): not clean',
                 f'skip worktree {dev}/wt-unpushed (o/r#7 merged): HEAD is on no remote branch',
                 f'skip worktree {dev}/wt-busy (o/r#7 merged): not clean: ?? untracked; a process has it open',
                 f'skip worktree {dev}/wt-private (o/r#7 merged): ignored files that may not rebuild: tmp',
                 f'skip worktree {dev}/wt-merged (o/r#7 merged): another checkout is inside it',
                 f'skip worktree {dev}/wt-grants (o/r#7 merged): ignored files that may not rebuild: .claude/settings.local.json\n',
                 f'removed worktree {dev}/wt-nest/.worktrees/agent (in {dev}/wt-nest, o/r#7 merged)',
                 f'skip worktree {dev}/wt-hold/.worktrees/wip (in {dev}/wt-hold, o/r#7 merged): not clean: ?? untracked',
                 f'skip worktree {dev}/wt-locked/.worktrees/session (in {dev}/wt-locked, o/r#7 merged): locked: no reason given',
                 f'skip worktree {dev}/wt-hold (o/r#7 merged): ignored files that may not rebuild: .worktrees/; another checkout is inside it',
                 f'skip worktree {dev}/wt-secret/.worktrees/inner (o/r#7 merged): not clean',
                 f'skip worktree {dev}/wt-secret (o/r#7 merged): ignored files that may not rebuild: .env, .worktrees/; '
                 'another checkout is inside it',
                 f'skip worktree {dev}/wt-fresh (o/r#7 merged): its tmp/ changed in the last 24 h',
                 f'skip worktree {dev}/wt-apm-mine (o/r#7 merged): ignored files that may not rebuild: .claude/skills/mine/SKILL.md\n',
                 f'skip worktree {dev}/wt-held (o/r#7 merged): a process has it open',
                 f'skip worktree {dev}/wt-deep-tmp (o/r#7 merged): its tmp/ changed in the last 24 h',
                 f'skip worktree {dev}/wt-bootstrap (o/r#7 merged): not clean: ?? project.yml; '
                 'its .bootstrap-state/ changed in the last 24 h\n',
                 f'skip worktree {dev}/wt-xcode (o/r#7 merged): not clean: ?? project.yml; '
                 'ignored files that may not rebuild: App.xcodeproj/, fake/\n',
                 f'skip worktree {dev}/wt-apm-bad (o/r#7 merged): ignored files that may not rebuild: .agents/skills/, .claude/skills/\n',
                 f'skip worktree {dev}/wt-many (o/r#7 merged): not clean: ?? notes.txt; '
                 'ignored files that may not rebuild: .env, id.key, private/\n',
                 f'skip worktree {dev}/wt-lockmix (o/r#7 merged): not clean: ?? locks/\n',
                 f'skip worktree {dev}/wt-notgen (o/r#7 merged): ignored files that may not rebuild: '
                 'gen_half.py, gen_later.py, gen_link.py\n',
                 f'skip env {dev}/recent/.venv: changed 0 days ago',
                 f'skip env {dev}/busy-env/.venv: a process names it',
                 f'skip env {dev}/linked/.venv: a symlink to elsewhere'):
        assert line in out, (line, out)
    assert f'removed worktree {dev}/wt-prmerged (o/r#9 closed)' in out, out
    assert 'wt-open' not in out and 'wt-propen' not in out and 'wt-prnone' not in out and 'wt-prearly' not in out and 'delete' not in (home / 'xcrun.calls').read_text()
    # One question per kept merged worktree that may hold something wanted, asked once.
    assert len(told) == 2 and 'Which may go?' in told[1] and 'simulator' not in told[1], told
    for path in ('wt-dirty', 'wt-unpushed', 'wt-private', 'wt-secret/.worktrees/inner', 'wt-apm-mine', 'wt-many'):
        assert f'- worktree {dev}/{path} (o/r#7 merged)' in told[1], (path, told[1])
    for outer, inner in (('hold', 'wip'), ('locked', 'session')):
        assert f'- worktree {dev}/wt-{outer}/.worktrees/{inner} (in {dev}/wt-{outer}, o/r#7 merged)' in told[1], told[1]
    # In use or holding another checkout settles by itself: kept, no question.
    assert not any(f'{dev}/{path} ' in told[1] for path in ('wt-busy', 'wt-merged', 'wt-secret', 'wt-squashed', 'wt-fresh', 'wt-prmerged', 'wt-prnone', 'wt-prearly',
                                                            'wt-held')), told[1]
    code, out = run('--floor-gb', '0')
    assert code == 0 and len(told) == 2, told
    code, out = run('--floor-gb', '1e9')
    assert code == 2 and len(told) == 3 and 'Low disk' in told[2] and 'Which may go?' not in told[2], out
    code, out = run('--floor-gb', '1e9')
    assert code == 2 and len(told) == 3 and 'already told' in out, out
    stamp, six_hours_ago = home / '.local/state/disk-hygiene/warned', time.time() - 6 * 3600
    os.utime(stamp, (six_hours_ago, six_hours_ago))
    (home / 'simulators.json').write_text('{"devices": {"iOS-17-0": [{"name": "iPhone 15"}]}}')
    code, out = run('--floor-gb', '1e9')  # a fresh question alone must not restart the warning's clock
    assert code == 2 and len(told) == 4 and 'Low disk' not in told[3] and '1 simulator devices' in told[3], told
    assert abs(stamp.stat().st_mtime - six_hours_ago) < 5, 'only a low-disk warning moves the warned stamp'
    (home / 'lsof.txt').unlink()  # a failed step under the floor still exits 1
    code, out = run('--floor-gb', '1e9')
    assert code == 1 and 'already told' in out, out
    assert len(list((home / '.local/state/disk-hygiene').glob('*.log'))) >= 1
    stale_check(home, dev, git, run, told, hygiene)
    drift_check(home, run, told, hygiene)


def stale_check(home, dev, git, run, told, hygiene):
    """A script that differs from the checkout's origin/main is told once per pair of versions."""
    script = SCRIPT
    with (home / '.gitconfig').open('a') as config:
        config.write(f'[url "{home}/self.git"]\n\tinsteadOf = https://github.com/o/self.git\n')
    git(home, 'init', '-q', '--bare', 'self.git')
    checkout = home / 'self'
    (checkout / hygiene.SELF).parent.mkdir(parents=True)
    git(checkout, 'init', '-q', '-b', 'main')
    git(checkout, 'remote', 'add', 'origin', 'https://github.com/o/self.git')
    copy = checkout / hygiene.SELF
    copy.write_bytes(script.read_bytes())
    git(checkout, 'add', '.')
    git(checkout, 'commit', '-q', '-m', 'same')
    git(checkout, 'push', '-q', 'origin', 'main')
    hygiene.REPO = checkout
    (home / 'lsof.txt').write_text(f'p1\nfcwd\nn{dev}/wt-busy\np2\nf3\nn{dev}/wt-held/held.lock\n')  # as before its failure
    before = len(told)
    code, out = run('--floor-gb', '0')
    assert code == 0 and 'STALE' not in out and len(told) == before, out
    copy.write_bytes(script.read_bytes() + b'# released\n')
    (checkout / 'added').write_text('x')  # a release also adds a file
    git(checkout, 'add', '.')
    git(checkout, 'commit', '-q', '-m', 'release')
    git(checkout, 'push', '-q', 'origin', 'main')
    git(checkout, 'reset', '-q', '--hard', 'HEAD~1')  # the run reads origin/main, not the checkout
    relaunched = []
    real_execv, os.execv = os.execv, lambda *argv: relaunched.append(argv)  # the real one replaces this process
    copy.write_bytes(copy.read_bytes() + b'# mine\n')  # a modified tracked file is a person's to handle: nothing moves
    code, out = run('--floor-gb', '0')
    assert code == 0 and 'STALE: This disk-hygiene' in out and len(told) == before + 1 and not relaunched, out
    git(checkout, 'checkout', '-q', '--', hygiene.SELF)
    code, out = run('--dry-run', '--floor-gb', '0')  # a dry run moves nothing
    assert 'STALE' in out and not relaunched, out
    git(checkout, 'checkout', '-q', '-b', 'topic')  # another branch: nothing moves
    code, out = run('--floor-gb', '0')
    assert 'STALE' in out and not relaunched, out
    git(checkout, 'checkout', '-q', 'main')
    git(checkout, 'commit', '-q', '--allow-empty', '-m', 'local')  # diverged: no fast-forward exists
    code, out = run('--floor-gb', '0')
    assert 'STALE' in out and not relaunched, out
    git(checkout, 'reset', '-q', '--hard', 'HEAD~1')
    (checkout / 'added').write_text('mine')  # untracked, but main adds it: ff-only refuses and changes nothing
    code, out = run('--floor-gb', '0')
    assert 'STALE' in out and not relaunched and (checkout / 'added').read_text() == 'mine', out
    assert git(checkout, 'rev-parse', 'HEAD') != git(checkout, 'rev-parse', 'origin/main')
    (checkout / 'added').unlink()
    (checkout / 'untracked-only').write_text('x')  # untracked and not in main: no block
    hygiene.DOTAGENTS = installer = home / 'self-install'
    installer.write_text(f'#!/bin/sh\necho "$@" >> {home}/install.calls\n')
    installer.chmod(0o755)
    code, out = run('--floor-gb', '0')  # clean, on main, behind: fast-forward, install, run the new copy
    assert code == 0 and 'STALE' not in out and len(relaunched) == 1 and len(told) == before + 1, out
    assert (home / 'install.calls').read_text().startswith('install --no-pull\n'), 'a fast-forward installs what it moved'
    assert (checkout / 'untracked-only').exists() and (checkout / 'added').exists()
    assert relaunched[0][0] == sys.executable and relaunched[0][1][0] == sys.executable, relaunched
    assert os.environ.pop('DISK_HYGIENE_RELAUNCHED') == '1', 'the relaunched copy must not fast-forward again'
    assert copy.read_bytes().endswith(b'# released\n') and git(checkout, 'rev-parse', 'HEAD') == git(checkout, 'rev-parse', 'origin/main')
    git(checkout, 'reset', '-q', '--hard', 'HEAD~1')
    installer.write_text('#!/bin/sh\necho boom >&2\nexit 3\n')  # a failed install is reported; the run still starts over
    code, out = run('--floor-gb', '0')
    assert 'FAIL dotagents install after a fast-forward: exit 3: boom' in out and len(relaunched) == 2, out
    code, out = run('--floor-gb', '0')  # the relaunched copy: a new Run that must still end in failure
    assert code == 1 and 'FAIL dotagents install after a fast-forward: exit 3: boom' in out, out
    os.environ.pop('DISK_HYGIENE_RELAUNCHED')
    git(checkout, 'reset', '-q', '--hard', 'HEAD~1')
    os.environ['DISK_HYGIENE_RELAUNCHED'] = '1'  # a relaunched run that still differs must not loop
    code, out = run('--floor-gb', '0')
    del os.environ['DISK_HYGIENE_RELAUNCHED']
    os.execv = real_execv
    assert 'STALE' in out and len(relaunched) == 2 and len(told) == before + 1, 'told once per pair of versions'
    assert "is not origin/main's" in told[-1] and 'Which may go?' not in told[-1], told[-1]
    git(checkout, 'reset', '-q', '--hard', 'origin/main')  # a release that leaves the script alone still fast-forwards and installs
    copy.write_bytes(script.read_bytes())  # the script is the running one again: only 'docs' is new
    (checkout / 'docs').write_text('x')
    git(checkout, 'add', '.')
    git(checkout, 'commit', '-q', '-m', 'docs release')
    git(checkout, 'push', '-q', 'origin', 'main')
    git(checkout, 'reset', '-q', '--hard', 'HEAD~1')
    installer.write_text(f'#!/bin/sh\necho "$@" >> {home}/install.calls\n')
    installs = lambda: [l for l in (home / 'install.calls').read_text().splitlines() if l.startswith('install')]
    before_installs, before_relaunches = len(installs()), len(relaunched)
    os.execv = lambda *argv: relaunched.append(argv)
    code, out = run('--floor-gb', '0')
    assert 'STALE' not in out and len(installs()) == before_installs + 1 and len(relaunched) == before_relaunches, out
    assert git(checkout, 'rev-parse', 'HEAD') == git(checkout, 'rev-parse', 'origin/main') and (checkout / 'docs').exists()
    code, out = run('--floor-gb', '0')  # up to date: nothing to install
    assert len(installs()) == before_installs + 1 and len(relaunched) == before_relaunches, out
    os.execv = real_execv
    copy.write_bytes(script.read_bytes() + b'# released again\n')
    git(checkout, 'commit', '-q', '-am', 'release again')
    git(checkout, 'push', '-q', '-f', 'origin', 'main')  # the cached origin/main moves; the remote then goes away
    (home / 'self.git').rename(home / 'self.gone')
    code, out = run('--floor-gb', '0')
    assert 'STALE' not in out and len(told) == before + 1, 'a failed fetch makes no claim'
    hygiene.REPO = home / 'no-checkout'


def drift_check(home, run, told, hygiene):
    """dotagents doctor's findings are told once each; a clean doctor adds nothing; a broken one fails the run."""
    doctor = hygiene.DOTAGENTS = home / 'doctor/dotagents'
    doctor.parent.mkdir(parents=True)
    findings = 'too old: gh 2.87.0, skill demo needs >= 2.99.0\nstale skill copy: /x/.claude/skills/demo: post_demo.sh'
    for body, wanted in ((f"printf '%s\\n' '{findings}'; exit 1", 0), ('exit 0', 0), ('echo broken >&2; exit 1', 1),
                         ('exit 3', 1), ('echo "dotagents: unknown command: doctor" >&2; exit 2  # usage', 0)):
        doctor.write_text(f'#!/bin/sh\n[ "$1" = doctor ] || exit 9\n{body}\n')
        doctor.chmod(0o755)
        before = len(told)
        code, out = run('--floor-gb', '0')
        assert code == wanted, (body, out)
        if 'usage' in body:
            assert 'has no doctor command' in told[-1] and len(told) == before + 1, (out, told[-1:])
        elif 'printf' in body:
            assert 'DRIFT: too old: gh 2.87.0' in out and len(told) == before + 1, out
            assert '- too old: gh 2.87.0, skill demo needs >= 2.99.0' in told[-1] and 'post_demo.sh' in told[-1], told[-1]
            code, out = run('--floor-gb', '0')
            assert code == 0 and 'DRIFT: too old' in out and len(told) == before + 1, 'each finding told once'
        else:
            assert len(told) == before and 'DRIFT' not in out, (body, out)
            assert ('FAIL dotagents doctor' in out) is bool(wanted), (body, out)
    doctor.unlink()


def test_tell(tmp_path, monkeypatch):
    """tell() finds the chief of staff on a server other than the CLI's default and posts only there."""
    home = tmp_path.resolve()
    monkeypatch.setenv('HOME', str(home))
    hygiene = load('disk_hygiene_tell')
    posts = []

    seen = []  # (port, path, Authorization) of every request

    def serve(sessions, redirect=None, detail_status=200, echo=False, garbled=False):
        class Handler(http.server.BaseHTTPRequestHandler):
            def reply(self, body):
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                seen.append((self.server.server_port, self.path, self.headers['Authorization']))
                if garbled:  # not HTTP at all, quoting the token: the parser's error would carry it
                    self.wfile.write(f'invalid {self.headers["Authorization"]}\r\n'.encode())
                elif echo:  # a hostile or broken server puts the token it got into its error text
                    self.send_response(401, 'rejected ' + self.headers['Authorization'])
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                elif redirect:
                    self.send_response(302)
                    self.send_header('Location', redirect + self.path)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                elif self.path.startswith('/v1/sessions?'):
                    self.reply({'data': sessions})
                elif detail_status != 200:
                    self.send_error(detail_status)
                else:
                    self.reply({'runner_online': True})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                posts.append((self.server.server_port, self.path, self.headers['Authorization'], body))
                self.reply({})

            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server
    personal = serve([{'id': 'old', 'labels': {'omni.role': 'cos'}, 'archived': True},
                      {'id': 'cos1', 'labels': {'omni.role': 'cos'}}])
    work = serve([{'id': 'other', 'labels': {'omni.role': 'lead'}}])
    # Tried before personal: one redirects there (its token must not follow), one fails after listing a cos.
    moved = serve([], redirect=f'http://127.0.0.1:{personal.server_port}')
    broken = serve([{'id': 'cos9', 'labels': {'omni.role': 'cos'}}], detail_status=503)
    echo = serve([], echo=True)
    garbled = serve([], garbled=True)
    urls = {name: f'http://127.0.0.1:{server.server_port}' for name, server in
            (('work', work), ('personal', personal), ('moved', moved), ('broken', broken), ('echo', echo),
             ('garbled', garbled))}
    (home / '.omnigent').mkdir(exist_ok=True)
    (home / '.omnigent/config.yaml').write_text(f'host:\n  name: devbox\nserver: {urls["work"]}\n')
    hygiene.OMNIGENT_PYTHON = sys.executable  # LOGINS below stands in for the Omnigent tool's token lookup
    hygiene.LOGINS = (f'import json, sys; tokens = {{s: "t-" + s[-5:] for s in sys.argv[1:] + {json.dumps([urls["garbled"], urls["echo"], urls["moved"], urls["broken"], urls["personal"]])}}}; '
                      'print(json.dumps(tokens))')
    try:
        where = hygiene.tell('hello')
        assert where == f'cos1 on {urls["personal"]}', where
        assert [(port, path) for port, path, _, _ in posts] == [(personal.server_port, '/v1/sessions/cos1/events')], posts
        assert posts[0][2] == f'Bearer t-{urls["personal"][-5:]}', 'each server gets its own token'
        assert posts[0][3]['data']['content'][0]['text'] == 'hello'
        assert not [r for r in seen if r[0] == personal.server_port and r[2] != f'Bearer t-{urls["personal"][-5:]}'], \
            ('a redirect carried another server\'s token', seen)
        assert any(r[0] == broken.server_port and r[1] == '/v1/sessions/cos9' for r in seen), 'broken was tried'
        personal.shutdown()
        personal.server_close()
        try:
            hygiene.tell('again')
            raise AssertionError('tell() must raise when no server holds the chief of staff')
        except RuntimeError as error:
            assert f'{urls["work"]}: none' in str(error) and urls['personal'] in str(error), error
            assert f'{urls["echo"]}: HTTP 401' in str(error) and 'Bearer' not in str(error), ('a token in the error', error)
            assert f'{urls["garbled"]}: BadStatusLine' in str(error), error
        assert len(posts) == 1, posts
    finally:
        for server in (work, moved, broken, echo, garbled):
            server.shutdown()
            server.server_close()



def test_dead_terminals(tmp_path, monkeypatch):
    """Real child processes stand in for terminal wrappers; only their ppid is faked, since a test's children are not orphans."""
    hygiene = load('disk_hygiene_terminals')
    monkeypatch.setattr(hygiene, 'GRACE', 0.3)
    script = tmp_path / 'omnigent/terminals/program_status.py'
    script.parent.mkdir(parents=True)
    script.write_text('import signal, subprocess, sys, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)  # as the real wrapper\n'
                      'subprocess.Popen(["sleep", "60"])  # its claude\ntime.sleep(60)\n')
    alive_dir, gone = tmp_path / 'claude-native/cafe01', tmp_path / 'claude-native/dead01'
    alive_dir.mkdir(parents=True)
    odd = tmp_path / 'my dir/claude-native/cafe02'  # exists, but a flattened command line cannot say where the path ends
    odd.mkdir(parents=True)
    spawn = lambda *argv: subprocess.Popen(argv, start_new_session=True)
    kids = {
        'dead': spawn(sys.executable, script, '--app', 'x', '--bridge-dir', str(gone)),
        'json': spawn(sys.executable, script, '--mcp-config', f'{{"args":["--bridge-dir","{gone}"]}}'),
        'live': spawn(sys.executable, script, '--bridge-dir', str(alive_dir)),
        'nodir': spawn(sys.executable, script),
        'other': spawn('sh', '-c', 'sleep 60', 'x', '--bridge-dir', str(gone)),  # not a wrapper
        'tmux': spawn(sys.executable, '-c', 'import time; time.sleep(60)', str(script), '--bridge-dir', str(gone)),  # only names it
        'space': spawn(sys.executable, script, '--bridge-dir', str(odd)),
        'escaped': spawn(sys.executable, script, '--mcp-config', '{"args":["--bridge-dir","/tmp/Jos\\u00e9/claude-native/dead02"]}'),
        'otheruser': spawn(sys.executable, script, '--bridge-dir', str(gone)),  # another account's wrapper
        'second': spawn(sys.executable, script, '--bridge-dir', str(gone), '--bridge-dir', str(alive_dir)),  # one of two dirs exists
        'shared': spawn(sys.executable, script, '--bridge-dir', str(gone)),  # a dead wrapper in a group it does not lead
        'parented': spawn(sys.executable, script, '--bridge-dir', str(gone)),  # still has its parent
    }
    bystander = spawn('sleep', '60')  # leads the group the 'shared' wrapper claims to be in
    orphans = {kids[k].pid for k in kids if k != 'parented'}
    real = hygiene.listing
    extra = []  # rows a test adds to the real listing

    def fake():
        rows = []
        for pid, ppid, uid, pgid, z, command in real():
            if pid == kids['otheruser'].pid:
                uid += 1
            if pid == kids['shared'].pid:
                pgid = bystander.pid
            rows.append((pid, 1 if pid in orphans else ppid, uid, pgid, z, command))
        return rows + extra
    monkeypatch.setattr(hygiene, 'listing', fake)
    monkeypatch.setattr(hygiene, 'pty_state', lambda: (50, 100))
    try:
        time.sleep(0.5)  # let the wrappers install their handler and start their child
        dry = hygiene.Run(True, tmp_path / 'dry.log')
        hygiene.dead_terminals(dry)
        out = (tmp_path / 'dry.log').read_text()
        assert all(p.poll() is None for p in kids.values())
        assert all(f'would kill dead terminal {kids[k].pid}' in out for k in ('dead', 'json', 'shared'))
        assert out.count('would kill') == 3 and 'terminals: 3 dead of ' in out and 'ptys 50/100' in out and 'WARN' not in out

        run = hygiene.Run(False, tmp_path / 'run.log')
        hygiene.dead_terminals(run)
        for name in ('dead', 'json', 'shared'):
            assert kids[name].wait(5) == -signal.SIGKILL  # it ignores SIGTERM
        assert {k for k, p in kids.items() if p.poll() is None} == {'live', 'nodir', 'other', 'tmux', 'parented', 'space', 'escaped', 'otheruser', 'second'} and bystander.poll() is None
        out = (tmp_path / 'run.log').read_text()
        assert 'terminals after: ptys 50/100' in out and not run.failed
        assert not [r for r in real() if r[5].startswith('sleep 60') and r[3] in (kids['dead'].pid, kids['json'].pid)]  # the group went

        monkeypatch.setattr(hygiene, 'pty_state', lambda: (81, 100))
        extra += [(900000 + i, 1, 0, 0, True, '') for i in range(25)]
        hygiene.dead_terminals(hygiene.Run(True, tmp_path / 'warn.log'))
        warned = (tmp_path / 'warn.log').read_text()
        assert 'WARN terminals: 81 ptys of 100' in warned and re.search(r'WARN terminals: (2[5-9]|[3-9]\d) zombies', warned)  # the host may have a zombie of its own

        monkeypatch.setattr(hygiene, 'listing', lambda: None)  # ps fails: nothing is killed and the run fails
        failed = hygiene.Run(False, tmp_path / 'fail.log')
        hygiene.dead_terminals(failed)
        assert failed.failed and 'FAIL terminals' in (tmp_path / 'fail.log').read_text()
    finally:
        for p in (*kids.values(), bystander):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGKILL)
            p.wait()
