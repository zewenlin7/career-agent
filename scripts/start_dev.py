"""Local supervisor: pinned dependency checks, migration, then two services. No provider calls."""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy.engine import make_url

from career_agent.config import Settings
from career_agent.resume.fonts import FontDependencyError, verified_fonts
from career_agent.resume.renderer import TypstRenderer

ROOT = Path(__file__).resolve().parents[1]


def check_dependencies(settings: Settings) -> bool:
    """Return whether the controlled font cache needs first-time installation."""
    import tempfile

    if make_url(settings.database_url.get_secret_value()).host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise RuntimeError("本地启动仅支持本机数据库，请检查数据库配置。")
    if not shutil.which("docker") or not shutil.which("npm"):
        raise RuntimeError("请先安装 Docker Compose 与 Node.js/npm。")
    if not (ROOT / "frontend/node_modules").is_dir():
        raise RuntimeError("请先在 frontend 运行 npm ci。")
    # Do not download an unpinned compiler; report the exact required version.
    renderer = TypstRenderer(settings.typst_bin, font_dir=settings.font_dir)
    with tempfile.TemporaryDirectory() as directory:
        result = renderer._run(["--version"], Path(directory))
        if (
            not result.stdout.startswith(b"typst 0.15.1 ")
            and result.stdout.strip() != b"typst 0.15.1"
        ):
            raise RuntimeError("请手动安装 Typst 0.15.1，并确保 typst 在 PATH 中。")
    try:
        verified_fonts(settings.font_dir)
    except FontDependencyError as exc:
        if str(exc) == "font_dependency_missing":
            return True
        raise RuntimeError("字体校验失败，请核对受控字体目录；不会使用系统字体。") from None
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Offline dependency check only")
    args = parser.parse_args()
    os.chdir(ROOT)
    children: list[subprocess.Popen[bytes]] = []
    stop = False

    def interrupt(signum: int, frame: object) -> None:
        nonlocal stop
        stop = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupt)
    try:
        settings = Settings()
        missing = check_dependencies(settings)
        if args.check:
            if missing:
                raise RuntimeError("字体尚未安装；正常启动将使用固定来源安装并校验。")
            subprocess.run([sys.executable, "scripts/setup_resume_fonts.py", "--check"], check=True)
            print("本地依赖检查通过。")
            return
        subprocess.run(["docker", "compose", "up", "-d", "postgres"], check=True)
        for _ in range(60):
            if stop:
                return
            ready = subprocess.run(
                ["docker", "compose", "exec", "-T", "postgres", "pg_isready", "-U", "career"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL 尚未就绪。")
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        subprocess.run(
            [sys.executable, "scripts/setup_resume_fonts.py", *([] if missing else ["--check"])],
            check=True,
        )
        import secrets

        token = (
            settings.ops_token.get_secret_value()
            if settings.ops_token
            else secrets.token_urlsafe(32)
        )
        env = {**os.environ, "CAREER_AGENT_OPS_TOKEN": token, "CAREER_AGENT_OPS_ENABLED": "true"}
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "career_agent.api.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                    "--no-access-log",
                ],
                env=env,
                start_new_session=True,
            )
        )
        children.append(
            subprocess.Popen(
                ["npm", "run", "dev", "--", "--port", "3000"],
                cwd=ROOT / "frontend",
                env={
                    **env,
                    "CAREER_AGENT_API_ORIGIN": "http://127.0.0.1:8000",
                    "NEXT_TELEMETRY_DISABLED": "1",
                },
                start_new_session=True,
            )
        )
        print(
            "前端：http://127.0.0.1:3000\n后端：http://127.0.0.1:8000/docs\n"
            "Ctrl+C 停止前后端；PostgreSQL 数据与容器保留。",
            flush=True,
        )
        while not stop:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("服务已退出，请检查本地端口与服务配置。")
            time.sleep(0.5)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print(
            "启动失败，请检查本地依赖、端口和配置；未输出密钥。Typst 需要固定版本 0.15.1。",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()


if __name__ == "__main__":
    main()
