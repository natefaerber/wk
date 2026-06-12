"""Story D — onboarding: actionable empty `switch` + `wk doctor`."""

from __future__ import annotations

import subprocess

import pytest
import typer


def _no_workspaces(wk, monkeypatch, *, tty: bool):
    monkeypatch.setattr(wk, "require", lambda *a, **k: None)
    monkeypatch.setattr(wk, "all_workspaces", lambda: [])
    monkeypatch.setattr(wk.sys.stdin, "isatty", lambda: tty)


def test_switch_empty_headless_dies(wk, monkeypatch):
    # Piped/headless with no workspaces must still fail (scripts depend on it).
    _no_workspaces(wk, monkeypatch, tty=False)
    with pytest.raises(typer.Exit):
        wk.switch(None)


def test_switch_empty_interactive_cancel_does_not_create(wk, monkeypatch):
    _no_workspaces(wk, monkeypatch, tty=True)
    monkeypatch.setattr(wk.typer, "prompt", lambda *a, **k: "")  # user cancels
    created = []
    monkeypatch.setattr(wk, "open_ref", lambda *a, **k: created.append(a))
    with pytest.raises(typer.Exit):
        wk.switch(None)
    assert not created


def test_switch_empty_interactive_creates_first_workspace(wk, monkeypatch):
    _no_workspaces(wk, monkeypatch, tty=True)
    monkeypatch.setattr(wk.typer, "prompt", lambda *a, **k: "feat/first")
    created = []
    monkeypatch.setattr(wk, "open_ref", lambda *a, **k: created.append(a))
    wk.switch(None)  # returns after kicking off creation
    assert created and created[0][0] == "feat/first"


def _all_tools_present(wk, monkeypatch):
    monkeypatch.setattr(wk.shutil, "which", lambda t: f"/usr/bin/{t}")


def test_doctor_reports_bindings_loaded(wk, monkeypatch, capsys):
    _all_tools_present(wk, monkeypatch)
    monkeypatch.setattr(
        wk, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "1\n", "")
    )
    wk.doctor()
    assert "loaded" in capsys.readouterr().out


def test_doctor_warns_when_bindings_not_loaded(wk, monkeypatch, capsys):
    _all_tools_present(wk, monkeypatch)
    monkeypatch.setattr(
        wk, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", "")
    )
    wk.doctor()
    assert "not loaded" in capsys.readouterr().out


def test_doctor_exits_nonzero_when_required_tool_missing(wk, monkeypatch):
    # git missing → required failure → exit 1.
    monkeypatch.setattr(wk.shutil, "which", lambda t: None if t == "git" else f"/usr/bin/{t}")
    monkeypatch.setattr(
        wk, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "1\n", "")
    )
    with pytest.raises(typer.Exit):
        wk.doctor()
