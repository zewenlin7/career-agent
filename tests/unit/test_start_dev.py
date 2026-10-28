import runpy
from types import SimpleNamespace

import pytest

from career_agent.config import Settings
from career_agent.resume.fonts import FontDependencyError


def preflight(monkeypatch, tmp_path):
    function = runpy.run_path("scripts/start_dev.py")["check_dependencies"]
    env = function.__globals__
    (tmp_path / "frontend/node_modules").mkdir(parents=True)
    monkeypatch.setitem(env, "ROOT", tmp_path)
    monkeypatch.setattr(env["shutil"], "which", lambda name: "/test/" + name)
    monkeypatch.setattr(
        env["TypstRenderer"], "_run", lambda *args: SimpleNamespace(stdout=b"typst 0.15.1")
    )
    return function, env


def test_local_preflight_missing_fonts_is_installable_but_corrupt_fails(monkeypatch, tmp_path):
    check, env = preflight(monkeypatch, tmp_path)

    def missing(_):
        raise FontDependencyError("font_dependency_missing")

    monkeypatch.setitem(env, "verified_fonts", missing)
    assert check(Settings()) is True

    def corrupt(_):
        raise FontDependencyError("font_hash_mismatch")

    monkeypatch.setitem(env, "verified_fonts", corrupt)
    with pytest.raises(RuntimeError, match="字体校验失败"):
        check(Settings())
    monkeypatch.setitem(env, "verified_fonts", lambda _: [])
    assert check(Settings()) is False


def test_local_preflight_never_downloads_typst(monkeypatch, tmp_path):
    check, env = preflight(monkeypatch, tmp_path)
    monkeypatch.setattr(
        env["TypstRenderer"], "_run", lambda *args: SimpleNamespace(stdout=b"typst 0.14.0")
    )
    with pytest.raises(RuntimeError, match="手动安装 Typst 0.15.1"):
        check(Settings())


def test_supervisor_orders_preflight_and_cleans_children_without_printing_token(
    monkeypatch, capsys
):
    import signal

    function = runpy.run_path("scripts/start_dev.py")["main"]
    env = function.__globals__
    commands, children, stopped, handlers = [], [], [], {}
    monkeypatch.setattr(env["sys"], "argv", ["start-dev.sh"])
    monkeypatch.setitem(env, "check_dependencies", lambda settings: True)
    monkeypatch.setattr(env["signal"], "signal", lambda sig, fn: handlers.update({sig: fn}))
    monkeypatch.setattr(env["os"], "chdir", lambda _: None)
    monkeypatch.setattr(env["os"], "killpg", lambda pid, sig: stopped.append(pid))

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    class Process:
        def __init__(self, command, **kwargs):
            commands.append(command)
            self.pid = len(children) + 1
            self.environment = kwargs["env"]
            children.append(self)
            if len(children) == 2:
                handlers[signal.SIGINT](signal.SIGINT, None)

        def poll(self):
            return None

        def wait(self, **kwargs):
            return 0

    monkeypatch.setattr(env["subprocess"], "run", run)
    monkeypatch.setattr(env["subprocess"], "Popen", Process)
    function()
    assert commands[0] == ["docker", "compose", "up", "-d", "postgres"]
    assert "alembic" in commands[2] and commands[2][-2:] == ["upgrade", "head"]
    assert commands[3][-1] == "scripts/setup_resume_fonts.py"
    assert "uvicorn" in commands[4] and commands[5][:3] == ["npm", "run", "dev"]
    assert stopped == [2, 1]
    token = children[0].environment["CAREER_AGENT_OPS_TOKEN"]
    assert children[1].environment["CAREER_AGENT_OPS_TOKEN"] == token
    assert token not in capsys.readouterr().out


def test_cgstart_is_a_local_exec_wrapper():
    from pathlib import Path

    wrapper = Path("cgstart")
    assert wrapper.stat().st_mode & 0o111
    content = wrapper.read_text()
    assert 'exec "$(dirname "$0")/start-dev.sh" "$@"' in content
    assert "export" not in content and "curl" not in content
