#!/usr/bin/env python3
"""Local console for a running idev session.

Reads traces, delegation records, run.yaml and the hypothesis ledger.
The page can post tasks and messages. The conductor reads them on the
next turn and replies. This process does not sign and does not dispatch.

    console.py                         # open the page on 127.0.0.1:8765
    console.py pending                 # unread messages, for the conductor
    console.py reply --text "..."      # conductor reply; marks those read
    console.py live --add --feature F --step S --agent A [--shard X]
    console.py live --clear --feature F --step S [--shard X]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import delegation  # noqa: E402
import hypothesis  # noqa: E402
import safeyaml  # noqa: E402
import trace  # noqa: E402
from product_sink import product_repo, sink_dir  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TRACE_LIMIT = 40
TEXT_LIMIT = 8000
BODY_LIMIT = 32768

PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>中控台</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #050910;
    --panel: rgba(7, 18, 34, 0.82);
    --line: rgba(94, 240, 255, 0.32);
    --cyan: #5ef0ff;
    --violet: #a594ff;
    --amber: #ffc14a;
    --text: #e8f7ff;
    --muted: #8eafc6;
    --danger: #ff6b8a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    color: var(--text);
    font: 13px/1.45 ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    background:
      radial-gradient(1100px 480px at 8% -10%, rgba(94, 240, 255, 0.16), transparent 52%),
      radial-gradient(820px 420px at 100% 0%, rgba(165, 148, 255, 0.18), transparent 48%),
      linear-gradient(180deg, #0a1626, var(--bg) 42%, #071018);
  }
  .atmo {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    background-image:
      linear-gradient(rgba(94, 240, 255, 0.05) 1px, transparent 1px),
      linear-gradient(90deg, rgba(94, 240, 255, 0.05) 1px, transparent 1px);
    background-size: 42px 42px;
    mask-image: radial-gradient(circle at 50% 20%, #000 10%, transparent 78%);
  }
  .atmo::after {
    content: "";
    position: absolute;
    inset: -20%;
    background: repeating-linear-gradient(to bottom, transparent 0 3px, rgba(0, 0, 0, 0.16) 3px 4px);
    animation: scan 9s linear infinite;
    opacity: 0.45;
  }
  header, .now, .arch, .grid, .thread { position: relative; z-index: 1; }
  header {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: center;
    padding: 14px 18px;
    border-bottom: 1px solid var(--line);
    background: linear-gradient(90deg, rgba(94, 240, 255, 0.08), rgba(165, 148, 255, 0.06) 42%, transparent 75%);
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  header h1 { margin: 0; font-size: 18px; letter-spacing: 0.22em; font-weight: 600; }
  .sub { margin: 2px 0 0; color: var(--cyan); font-size: 11px; letter-spacing: 0.16em; }
  .core {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 1px solid var(--cyan);
    box-shadow: 0 0 12px var(--cyan);
    position: relative;
    flex: none;
  }
  .core::before, .core::after {
    content: "";
    position: absolute;
    inset: -7px;
    border-radius: 50%;
    border: 1px solid rgba(94, 240, 255, 0.55);
    border-left-color: transparent;
    animation: spin 3.4s linear infinite;
  }
  .core::after {
    inset: -13px;
    border-color: rgba(165, 148, 255, 0.6);
    border-right-color: transparent;
    animation-duration: 5.6s;
    animation-direction: reverse;
  }
  .core.hot { border-color: var(--amber); box-shadow: 0 0 16px var(--amber); }
  .core.hot::before { animation-duration: 1s; }
  .hud { display: flex; align-items: center; gap: 10px; }
  .chip {
    border: 1px solid var(--line);
    color: var(--cyan);
    padding: 3px 8px;
    letter-spacing: 0.12em;
    font-size: 11px;
  }
  #chip-live.hot { color: var(--amber); border-color: rgba(255, 193, 74, 0.7); }
  #fresh { margin: 0; color: var(--muted); font-size: 11px; }
  .grid { display: grid; grid-template-columns: 250px minmax(0, 1fr) 340px; gap: 12px; padding: 12px; }
  .panel, .thread {
    background: var(--panel);
    border: 1px solid var(--line);
    box-shadow: 0 0 24px rgba(94, 240, 255, 0.05), inset 0 0 0 1px rgba(255, 255, 255, 0.02);
    backdrop-filter: blur(8px);
  }
  .panel { min-height: 240px; max-height: 68vh; overflow: auto; }
  .panel h2, .thread h2, h3 { margin: 0; padding: 10px 12px 6px; font-size: 12px; letter-spacing: 0.18em; color: var(--cyan); }
  h3 { color: var(--violet); }
  .panel h2::before, .thread h2::before { content: "// "; color: var(--violet); }
  .row, .item { display: block; width: 100%; text-align: left; border: 0; border-bottom: 1px solid rgba(94, 240, 255, 0.1); background: transparent; padding: 8px 12px; font: inherit; color: inherit; }
  button.row { cursor: pointer; }
  button.row:hover { background: rgba(94, 240, 255, 0.06); }
  button.row.on { background: linear-gradient(90deg, rgba(94, 240, 255, 0.16), transparent 78%); box-shadow: inset 2px 0 0 var(--cyan); }
  .running {
    box-shadow: inset 2px 0 0 var(--amber);
    background-image: linear-gradient(100deg, transparent 20%, rgba(255, 193, 74, 0.12) 48%, transparent 76%);
    background-size: 220% 100%;
    animation: sweep 2.2s linear infinite;
  }
  .pulse {
    width: 8px;
    height: 8px;
    margin-right: 8px;
    border-radius: 50%;
    display: inline-block;
    vertical-align: middle;
    background: var(--amber);
    box-shadow: 0 0 8px var(--amber);
    animation: blink 1.15s ease-in-out infinite;
  }
  .name { font-weight: 600; color: var(--text); }
  .muted { color: var(--muted); font-size: 12px; }
  .group { padding: 8px 12px 0; color: var(--violet); font-size: 11px; letter-spacing: 0.14em; }
  .item.skill { box-shadow: inset 2px 0 0 var(--violet); }
  .item.hop { box-shadow: inset 2px 0 0 var(--cyan); }
  .hop-arrow { padding: 0 12px; color: var(--cyan); font-size: 12px; line-height: 1; }
  .thread { margin: 0 12px 12px; padding-bottom: 12px; }
  .msg { margin: 8px 12px; padding: 8px 10px 8px 42px; border: 1px solid rgba(94, 240, 255, 0.18); background: rgba(94, 240, 255, 0.05); white-space: pre-wrap; position: relative; }
  .msg::before { content: "AI"; position: absolute; left: 8px; top: 8px; font-size: 10px; letter-spacing: 0.08em; color: var(--violet); border: 1px solid rgba(165, 148, 255, 0.5); padding: 1px 4px; }
  .msg.user { border-color: rgba(94, 240, 255, 0.4); background: rgba(94, 240, 255, 0.08); }
  .msg.user::before { content: "YOU"; color: var(--cyan); border-color: rgba(94, 240, 255, 0.5); }
  .msg .who { display: block; color: var(--muted); font-size: 11px; margin-bottom: 2px; }
  form { display: grid; gap: 8px; padding: 0 12px; }
  textarea {
    width: 100%;
    min-height: 72px;
    padding: 8px;
    color: var(--text);
    background: rgba(3, 10, 18, 0.72);
    border: 1px solid var(--line);
    font: inherit;
    resize: vertical;
  }
  textarea:focus { outline: 1px solid var(--cyan); box-shadow: 0 0 12px rgba(94, 240, 255, 0.25); }
  button.send {
    justify-self: start;
    background: transparent;
    color: var(--cyan);
    border: 1px solid var(--cyan);
    letter-spacing: 0.16em;
    padding: 8px 16px;
    font: inherit;
    cursor: pointer;
  }
  button.send:hover { background: rgba(94, 240, 255, 0.12); box-shadow: 0 0 16px rgba(94, 240, 255, 0.25); }
  .note, .err { margin: 8px 12px 0; color: var(--muted); font-size: 12px; }
  .err { color: var(--danger); }
  dl { margin: 0; padding: 0 12px 8px; }
  dt { color: var(--violet); font-size: 11px; letter-spacing: 0.12em; margin-top: 8px; }
  dd { margin: 0; white-space: pre-wrap; }
  details { margin: 0 12px 8px; }
  summary { cursor: pointer; color: var(--cyan); }
  pre { margin: 4px 0 0; padding: 8px; background: rgba(3, 10, 18, 0.8); border: 1px solid rgba(94, 240, 255, 0.16); white-space: pre-wrap; word-break: break-word; font-size: 12px; max-height: 220px; overflow: auto; color: var(--text); }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes scan { to { transform: translateY(36px); } }
  @keyframes blink { 50% { opacity: 0.25; transform: scale(0.75); } }
  @keyframes sweep { to { background-position: -220% 0; } }
  .now, .arch { margin: 12px 12px 0; }
  .arch { overflow: auto; }
  .now-card {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 4px 18px;
    margin: 0 12px 12px;
    padding: 12px 14px;
    border: 1px solid var(--line);
    background: rgba(3, 10, 18, 0.55);
  }
  .now-card.running { border-color: rgba(255, 193, 74, 0.75); box-shadow: 0 0 18px rgba(255, 193, 74, 0.16); }
  .now-k { color: var(--muted); font-size: 11px; letter-spacing: 0.16em; }
  .now-title { font-size: 16px; letter-spacing: 0.03em; }
  .now-meta { color: var(--muted); font-size: 12px; }
  .stage-chip {
    justify-self: end;
    align-self: start;
    border: 1px solid var(--cyan);
    color: var(--cyan);
    letter-spacing: 0.18em;
    padding: 8px 12px;
    min-width: 88px;
    text-align: center;
  }
  .stage-chip b { display: block; color: var(--text); font-size: 15px; letter-spacing: 0.12em; margin-top: 2px; }
  .track { display: flex; flex-wrap: wrap; gap: 6px; grid-column: 1 / -1; margin-top: 6px; }
  .track span { border: 1px solid rgba(94, 240, 255, 0.2); color: var(--muted); padding: 2px 7px; font-size: 11px; letter-spacing: 0.08em; }
  .track .was { color: #7ee0aa; border-color: rgba(126, 224, 170, 0.45); }
  .track .on { color: var(--amber); border-color: var(--amber); box-shadow: 0 0 10px rgba(255, 193, 74, 0.25); }
  .work { grid-column: 1 / -1; margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255, 193, 74, 0.35); }
  .paths { margin: 6px 0 0; padding: 0; list-style: none; display: flex; flex-wrap: wrap; gap: 6px; }
  .paths li { border: 1px solid rgba(94, 240, 255, 0.28); color: var(--cyan); padding: 2px 7px; font-size: 11px; letter-spacing: 0.02em; }
  .arch-board {
    display: grid;
    grid-template-columns: minmax(128px, 0.8fr) 40px minmax(150px, 0.9fr) 40px minmax(240px, 1.5fr) 40px minmax(180px, 1fr);
    gap: 8px;
    padding: 4px 12px 12px;
    align-items: stretch;
    min-width: 920px;
  }
  .lane { display: flex; flex-direction: column; justify-content: center; gap: 8px; min-width: 0; }
  .lane h3 { padding: 0 0 2px; }
  .node {
    display: block;
    width: 100%;
    text-align: left;
    color: inherit;
    font: inherit;
    cursor: pointer;
    border: 1px solid rgba(94, 240, 255, 0.28);
    background: rgba(3, 10, 18, 0.62);
    padding: 8px 10px;
  }
  .node .role { color: var(--muted); font-size: 11px; margin-top: 2px; }
  .node.running { border-color: var(--amber); box-shadow: 0 0 16px rgba(255, 193, 74, 0.28); }
  .node.active { border-color: var(--cyan); box-shadow: 0 0 14px rgba(94, 240, 255, 0.22); }
  .node.pass { border-color: rgba(126, 224, 170, 0.75); }
  .node.fail { border-color: var(--danger); box-shadow: 0 0 12px rgba(255, 107, 138, 0.25); }
  .node.idle { opacity: 0.42; }
  .wires { display: flex; align-items: center; }
  .flow {
    width: 100%;
    height: 2px;
    background: repeating-linear-gradient(90deg, var(--cyan) 0 8px, transparent 8px 14px);
    background-size: 28px 2px;
    animation: march 0.7s linear infinite;
  }
  .wires.hot .flow { background-image: repeating-linear-gradient(90deg, var(--amber) 0 8px, transparent 8px 14px); }
  .wires.idle .flow { opacity: 0.28; animation: none; background: rgba(94, 240, 255, 0.35); }
  .legend { display: flex; flex-wrap: wrap; gap: 10px; padding: 0 12px 10px; color: var(--muted); font-size: 11px; letter-spacing: 0.08em; }
  .legend i { display: inline-block; width: 8px; height: 8px; margin-right: 4px; vertical-align: baseline; border: 1px solid var(--cyan); }
  .legend .lg-run { border-color: var(--amber); background: var(--amber); }
  .legend .lg-on { background: var(--cyan); }
  .legend .lg-ok { border-color: #7ee0aa; background: #7ee0aa; }
  .legend .lg-bad { border-color: var(--danger); background: var(--danger); }
  .meters { margin: 12px 12px 0; max-height: none; }
  .meter-lead { margin: 0 12px 8px; color: var(--muted); font-size: 12px; }
  .meter-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; padding: 0 12px 12px; }
  .meter {
    min-height: 138px;
    padding: 8px;
    border: 1px solid rgba(94, 240, 255, 0.28);
    background:
      linear-gradient(var(--cyan), var(--cyan)) 0 0 / 10px 1px no-repeat,
      linear-gradient(var(--cyan), var(--cyan)) 0 0 / 1px 10px no-repeat,
      linear-gradient(var(--violet), var(--violet)) 100% 0 / 10px 1px no-repeat,
      linear-gradient(var(--violet), var(--violet)) 100% 0 / 1px 10px no-repeat,
      linear-gradient(var(--cyan), var(--cyan)) 0 100% / 10px 1px no-repeat,
      linear-gradient(var(--cyan), var(--cyan)) 0 100% / 1px 10px no-repeat,
      linear-gradient(var(--violet), var(--violet)) 100% 100% / 10px 1px no-repeat,
      linear-gradient(var(--violet), var(--violet)) 100% 100% / 1px 10px no-repeat,
      rgba(3, 10, 18, 0.55);
  }
  .meter-k { color: var(--violet); font-size: 11px; letter-spacing: 0.16em; margin-bottom: 8px; }
  .cols { display: flex; align-items: flex-end; gap: 3px; height: 86px; }
  .col {
    flex: 1;
    min-width: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
    gap: 2px;
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .col i { display: block; width: 100%; background: linear-gradient(180deg, var(--cyan), rgba(94, 240, 255, 0.12)); box-shadow: 0 0 8px rgba(94, 240, 255, 0.35); }
  .col b { font-size: 10px; font-weight: 600; color: var(--text); min-height: 12px; }
  .col span { color: var(--muted); font-size: 10px; }
  .hbars { display: grid; gap: 3px; }
  .hbar {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr) auto;
    gap: 6px;
    align-items: center;
    width: 100%;
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
    text-align: left;
  }
  .hbar span { color: var(--muted); font-size: 11px; }
  .hbar u { display: block; height: 4px; background: rgba(94, 240, 255, 0.12); text-decoration: none; }
  .hbar u i { display: block; height: 100%; background: var(--cyan); box-shadow: 0 0 8px rgba(94, 240, 255, 0.45); }
  .hbar b { font-size: 11px; font-weight: 600; color: var(--amber); }
  .reads, .pips, .skill-hits { display: grid; gap: 6px; }
  .reads { grid-template-columns: 1fr 1fr; }
  .pips { grid-template-columns: 1fr 1fr; }
  .read, .pip, .skill-hit {
    border: 1px solid rgba(94, 240, 255, 0.22);
    background: rgba(94, 240, 255, 0.04);
    color: inherit;
    font: inherit;
    text-align: left;
    padding: 4px 6px;
    cursor: pointer;
  }
  .read b, .pip b { display: block; color: var(--cyan); font-size: 13px; letter-spacing: 0.04em; font-weight: 600; }
  .read span, .pip span, .skill-hit span { color: var(--muted); font-size: 11px; }
  .skill-hit { display: flex; justify-content: space-between; gap: 8px; }
  .skill-hit b { color: var(--cyan); font-weight: 600; }
  .read:hover, .pip:hover, .skill-hit:hover, .col:hover, .hbar:hover { border-color: var(--cyan); background: rgba(94, 240, 255, 0.08); }
  .col:hover { border-color: transparent; }
  #chip-retry.hot { color: var(--violet); border-color: rgba(165, 148, 255, 0.75); }
  .deck { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(300px, 0.95fr); gap: 12px; padding: 0 12px 12px; }
  .deck .thread, .deck .adjust { margin: 0; }
  .kinds { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 12px; }
  .kind {
    background: transparent;
    color: var(--muted);
    border: 1px solid rgba(94, 240, 255, 0.28);
    font: inherit;
    letter-spacing: 0.12em;
    padding: 6px 10px;
    cursor: pointer;
  }
  .kind.on { color: var(--bg); background: var(--cyan); border-color: var(--cyan); }
  .hint { margin: 8px 12px; color: var(--amber); font-size: 12px; min-height: 32px; }
  .adjust form label { display: grid; gap: 4px; color: var(--violet); font-size: 11px; letter-spacing: 0.14em; }
  .adjust input {
    width: 100%;
    padding: 8px;
    color: var(--text);
    background: rgba(3, 10, 18, 0.72);
    border: 1px solid var(--line);
    font: inherit;
  }
  .adjust input:focus { outline: 1px solid var(--cyan); box-shadow: 0 0 12px rgba(94, 240, 255, 0.25); }
  @keyframes march { to { background-position: 28px 0; } }
  @media (prefers-reduced-motion: reduce) {
    .atmo::after, .core::before, .core::after, .pulse, .running, .flow { animation: none; }
  }
  @media (max-width: 960px) {
    .grid, .deck, .meter-grid { grid-template-columns: 1fr; }
    .panel { max-height: none; }
    header { align-items: flex-start; }
    .wires { min-height: 18px; }
  }
</style>
</head>
<body>
<div class="atmo" aria-hidden="true"></div>
<header>
  <div class="brand">
    <span class="core" id="core" aria-hidden="true"></span>
    <div>
      <h1>中控台</h1>
      <p class="sub">idev · AI LINK</p>
    </div>
  </div>
  <div class="hud">
    <span class="chip" id="chip-window">WINDOW 0</span>
    <span class="chip" id="chip-retry">RETRY 0</span>
    <span class="chip" id="chip-live">LIVE 0</span>
    <p id="fresh">读取 trace、委派、假设台账</p>
  </div>
</header>
<section class="meters panel">
  <h2>计量</h2>
  <p class="meter-lead">最近窗口里的轮次，以及这些票上的委派和假设。件数，不是分数，没有阈值。点某一格，依据会带到下面的意见里。</p>
  <div class="meter-grid" id="meters"></div>
</section>
<section class="now panel">
  <h2>当前任务</h2>
  <div id="now"></div>
</section>
<section class="arch panel">
  <h2>系统架构</h2>
  <div class="arch-board" id="arch"></div>
  <div class="legend">
    <span><i class="lg-run"></i>进行中</span>
    <span><i class="lg-on"></i>本轮</span>
    <span><i class="lg-ok"></i>通过</span>
    <span><i class="lg-bad"></i>失败</span>
    <span><i></i>待命</span>
  </div>
</section>
<div class="grid">
  <section class="panel"><h2>各轮</h2><div id="traces"></div></section>
  <section class="panel"><h2>时间线</h2><div id="timeline"></div></section>
  <section class="panel"><h2>详情</h2><div id="detail"></div></section>
</div>
<div class="deck">
<section class="adjust panel" id="adjust">
  <h2>定向调整</h2>
  <div class="kinds" id="kinds"></div>
  <p class="hint" id="kind-hint"></p>
  <form id="adjust-form">
    <label>目标<input id="target" autocomplete="off"></label>
    <label>依据<input id="basis" autocomplete="off"></label>
    <textarea id="opinion" placeholder="写清要动哪一格。本页只把这句话交给下一轮导体。"></textarea>
    <button class="send" type="submit">写入意见</button>
  </form>
  <p class="note">改的是意见，不是关口本身。本页不派工，不写 sealed、accepted、aligned、resolved。</p>
</section>
<section class="thread">
  <h2>任务与对话</h2>
  <div id="thread"></div>
  <form id="composer">
    <textarea id="text" placeholder="下达任务，或接着说"></textarea>
    <button class="send" type="submit">发送</button>
  </form>
  <p class="note">下一轮由导体读取，按同一套停问和签字规则处理。本页不写 sealed、accepted、aligned、resolved。</p>
  <p class="err" id="err"></p>
</section>
</div>
<script>
const state = { board: {traces: [], features: {}, live: [], thread: [], meters: {}}, traceName: "", delegKey: "", liveKey: "", kind: "改关口", targetDirty: false };
const ADJUST = [
  ["改关口", "这一格的把关要收紧或放宽。改的是关口，不是把这一张票修完就算。"],
  ["改这一步", "这一步的入口、顺序或委派包不清楚。点名步骤和执行者。"],
  ["补观测", "耗时、技能、委派或跳转没记下。点名缺的是哪一层。"],
  ["质疑基线", "下游看到的事实和基线不一致。意见里写上证据路径。"],
];
let lastKey = "";

function spent(n) {
  if (n === null || n === undefined || n === "") return "";
  const v = Number(n);
  if (!Number.isFinite(v)) return "";
  if (v < 60) return v + "s";
  const m = Math.floor(v / 60);
  return m + "m" + String(v % 60).padStart(2, "0") + "s";
}

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (k === "class") node.className = v;
    else if (v != null) node.setAttribute(k, v);
  });
  (children || []).forEach(child => node.append(child == null ? "" : child));
  return node;
}

function tx(text) { return document.createTextNode(text == null ? "" : String(text)); }

function currentTrace() {
  const rows = state.board.traces || [];
  return rows.find(r => r.name === state.traceName) || rows[0] || null;
}

function currentFeature() {
  const tr = currentTrace();
  if (tr && tr.feature) return tr.feature;
  const live = (state.board.live || [])[0];
  return live ? live.feature : "";
}

function packOf(feature) {
  return (state.board.features || {})[feature] || {run: {steps: []}, delegations: [], hypotheses: [], ops_duration_s: null};
}

function delegKey(row) {
  return [row.step, row.attempt, row.shard || ""].join("|");
}

function liveKey(row) {
  return [row.feature, row.step, row.shard || ""].join("|");
}

function renderTraces() {
  const root = document.getElementById("traces");
  root.replaceChildren();
  const groups = new Map();
  (state.board.traces || []).forEach(tr => {
    const key = tr.feature || "-";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(tr);
  });
  if (!groups.size) {
    root.append(el("p", {class: "muted"}, [tx("还没有 trace")]));
    return;
  }
  groups.forEach((rows, feature) => {
    root.append(el("div", {class: "group"}, [tx(feature)]));
    rows.forEach(tr => {
      const on = tr.name === (currentTrace() || {}).name;
      const button = el("button", {class: "row" + (on ? " on" : ""), type: "button"}, [
        el("div", {class: "name"}, [tx(tr.intent || tr.name)]),
        el("div", {class: "muted"}, [tx((tr.at || "") + "  " + (tr.route || ""))]),
      ]);
      button.addEventListener("click", () => {
        state.traceName = tr.name;
        state.delegKey = "";
        state.liveKey = "";
        render();
      });
      root.append(button);
    });
  });
}

function renderTimeline() {
  const root = document.getElementById("timeline");
  root.replaceChildren();
  const feature = currentFeature();
  const pack = packOf(feature);
  const tr = currentTrace();
  root.append(el("h3", {}, [tx(feature && feature !== "-" ? feature : "未绑票")]));
  if (pack.run && pack.run.workflow_id) {
    root.append(el("p", {class: "muted"}, [tx(pack.run.workflow_id + "  " + (pack.run.status || ""))]));
  }
  const lives = (state.board.live || []).filter(r => r.feature === feature);
  const seen = new Set(lives.map(liveKey));
  ((state.board.current || {}).running || []).filter(r => r.feature === feature && r.agent && !seen.has(liveKey(r))).forEach(row => lives.push(row));
  if (!lives.length) root.append(el("p", {class: "muted"}, [tx("没有进行中的 agent")]));
  lives.forEach(row => {
    const label = row.shard ? row.step + "/" + row.shard : row.step;
    const on = state.liveKey === liveKey(row);
      const button = el("button", {class: "row running" + (on ? " on" : ""), type: "button"}, [
      el("div", {class: "name"}, [el("span", {class: "pulse", "aria-hidden": "true"}, []), tx("进行中  " + (row.agent || ""))]),
      el("div", {class: "muted"}, [
        tx([label, row.kind].filter(Boolean).join("  ") + "  "),
        el("span", {"data-elapsed": liveKey(row)}, [tx(spent(row.elapsed_s))]),
      ]),
    ]);
    button.addEventListener("click", () => { state.liveKey = liveKey(row); state.delegKey = ""; render(); });
    root.append(button);
  });
  const dels = pack.delegations || [];
  if (!dels.length) root.append(el("p", {class: "muted"}, [tx("没有委派留痕")]));
  dels.forEach(row => {
    const label = row.shard ? row.step + "/" + row.shard : row.step;
    const on = state.delegKey === delegKey(row);
    const button = el("button", {class: "row" + (on ? " on" : ""), type: "button"}, [
      el("div", {class: "name"}, [tx((row.agent || "") + "  " + (row.status || ""))]),
      el("div", {class: "muted"}, [tx([label, row.kind, spent(row.duration_s), row.evidence].filter(Boolean).join("  "))]),
    ]);
    button.addEventListener("click", () => { state.delegKey = delegKey(row); state.liveKey = ""; render(); });
    root.append(button);
  });
  root.append(el("h3", {}, [tx("技能调起")]));
  if (!tr) {
    root.append(el("p", {class: "muted"}, [tx("没有选中的一轮")]));
    return;
  }
  root.append(el("p", {class: "muted"}, [tx(tr.how || "")]));
  const skills = tr.skills || [];
  const calls = (tr.calls || []).filter(c => c.kind === "skill");
  if (!skills.length && !calls.length) root.append(el("p", {class: "muted"}, [tx("没有记下")]));
  skills.forEach(s => {
    root.append(el("div", {class: "item skill"}, [
      el("div", {class: "name"}, [tx(s.name)]),
      el("div", {class: "muted"}, [tx(s.why || s.path || "")]),
    ]));
  });
  calls.forEach(c => {
    const hop = [c.from, c.to].filter(Boolean).join(" → ");
    root.append(el("div", {class: "item skill"}, [
      el("div", {class: "name"}, [tx(c.name)]),
      el("div", {class: "muted"}, [tx([hop, c.thinking, spent(c.duration_s)].filter(Boolean).join("  "))]),
    ]));
  });
  const tools = (tr.calls || []).filter(c => c.from && c.to && (c.kind === "tool" || String(c.from).indexOf("react:") === 0));
  appendHops(root, "工具跳", tools);
}

function hopCalls(tr) {
  return ((tr && tr.calls) || []).filter(c => c.from && c.to);
}

function appendHops(root, title, calls) {
  root.append(el("h3", {}, [tx(title)]));
  if (!calls.length) {
    root.append(el("p", {class: "muted"}, [tx("没有记下")]));
    return;
  }
  calls.forEach((c, i) => {
    if (i) root.append(el("div", {class: "hop-arrow"}, [tx("↓")]));
    const bits = [c.why || c.thinking, c.result, c.duration_s ? spent(c.duration_s) : ""].filter(Boolean);
    root.append(el("div", {class: "item hop"}, [
      el("div", {class: "name"}, [tx(c.from + " → " + c.to)]),
      el("div", {class: "muted"}, [tx(bits.join("  "))]),
    ]));
  });
}

function field(root, label, value) {
  if (value == null || String(value).trim() === "") return;
  root.append(el("dt", {}, [tx(label)]));
  root.append(el("dd", {}, [tx(value)]));
}

function renderDetail() {
  const root = document.getElementById("detail");
  root.replaceChildren();
  const feature = currentFeature();
  const pack = packOf(feature);
  const tr = currentTrace();
  const dl = el("dl", {}, []);
  if (tr) {
    field(dl, "意图", tr.intent);
    field(dl, "路由", tr.route);
    field(dl, "为什么", tr.why);
    field(dl, "调起", tr.how);
    field(dl, "技能", tr.skills_line);
    field(dl, "循环", tr.react);
    field(dl, "跳转", tr.hops);
    field(dl, "打开", (tr.opened || []).join(" · "));
    field(dl, "思考", tr.thinking);
    field(dl, "停", tr.stop);
    field(dl, "下一步", tr.next);
  }
  const live = (state.board.live || []).find(r => liveKey(r) === state.liveKey);
  if (live) {
    dl.append(el("dt", {}, [tx("进行中")]));
    dl.append(el("dd", {}, [
      tx([live.agent, live.step, live.shard].filter(Boolean).join("  ") + "  "),
      el("span", {"data-elapsed": liveKey(live)}, [tx(spent(live.elapsed_s))]),
    ]));
    field(dl, "开始", live.started_at);
  }
  const deleg = (pack.delegations || []).find(r => delegKey(r) === state.delegKey);
  if (deleg) {
    field(dl, "执行者", deleg.agent);
    field(dl, "步骤", [deleg.step, deleg.kind, deleg.status, spent(deleg.duration_s)].filter(Boolean).join("  "));
    field(dl, "证据", deleg.evidence);
    const checks = deleg.checks || {};
    field(dl, "检查", Object.keys(checks).length ? Object.entries(checks).map(([k, v]) => k + "=" + v).join("  ") : "");
    field(dl, "建议", deleg.suggest);
  }
  root.append(dl);
  if (tr) appendHops(root, "追踪", hopCalls(tr));
  if (deleg) {
    const brief = el("details", {}, [el("summary", {}, [tx("委派包")]), el("pre", {}, [tx(JSON.stringify(deleg.brief || {}, null, 2))])]);
    const report = el("details", {}, [el("summary", {}, [tx("回报")]), el("pre", {}, [tx(JSON.stringify(deleg.report || {}, null, 2))])]);
    root.append(brief, report);
  }
  root.append(el("h3", {}, [tx("问题处理")]));
  const ops = pack.ops_duration_s;
  root.append(el("p", {class: "muted"}, [tx("排障耗时  " + (ops === null || ops === undefined ? "" : spent(ops)))]));
  const items = pack.hypotheses || [];
  if (!items.length) root.append(el("p", {class: "muted"}, [tx("没有假设")]));
  items.forEach(item => {
    root.append(el("div", {class: "item"}, [
      el("div", {class: "name"}, [tx((item.id || "") + "  " + (item.status || ""))]),
      el("div", {}, [tx(item.claim || "")]),
      el("div", {class: "muted"}, [tx(item.at || "")]),
    ]));
  });
}

function renderThread() {
  const root = document.getElementById("thread");
  root.replaceChildren();
  const rows = state.board.thread || [];
  if (!rows.length) root.append(el("p", {class: "muted"}, [tx("还没有任务")]));
  rows.forEach(msg => {
    const who = msg.role === "user" ? "人" : "导体";
    const box = el("div", {class: "msg " + (msg.role || "")}, [
      el("span", {class: "who"}, [tx(who + "  " + (msg.at || "") + (msg.status === "unread" ? "  未读" : ""))]),
      tx(msg.text || ""),
    ]);
    root.append(box);
  });
}

const AGENTS = [
  ["idev-deliver", "交付"],
  ["idev-coder", "编码"],
  ["idev-reviewer", "审查"],
  ["idev-verifier", "验证"],
  ["idev-ops", "排障"],
];
const MODULES = [
  ["deliver", "交付"],
  ["verify", "验证"],
  ["ops", "排障"],
  ["conventions", "规约"],
  ["handoff", "交出口"],
];

function archNode(title, role, status, onClick) {
  const button = el("button", {class: "node " + status, type: "button"}, [
    el("div", {class: "name"}, [
      status === "running" ? el("span", {class: "pulse", "aria-hidden": "true"}, []) : tx(""),
      tx(title),
    ]),
    el("div", {class: "role"}, [tx(role)]),
  ]);
  if (onClick) button.addEventListener("click", onClick);
  return button;
}

function wire(mode) {
  const kind = mode === "hot" || mode === "idle" ? mode : "on";
  return el("div", {class: "wires " + kind}, [el("div", {class: "flow"}, [])]);
}

function lastDelegation(agent) {
  const rows = (packOf(currentFeature()).delegations || []).filter(row => row.agent === agent);
  return rows.length ? rows[rows.length - 1] : null;
}

function runningJobs(name) {
  return ((state.board.current || {}).running || []).filter(row => row.agent === name && (!currentFeature() || row.feature === currentFeature()));
}

function agentState(name) {
  const live = (state.board.live || []).filter(row => row.agent === name && (!currentFeature() || row.feature === currentFeature()));
  const jobs = live.length ? live : runningJobs(name);
  if (jobs.length) {
    const row = jobs[0];
    const label = row.shard ? row.step + "/" + row.shard : row.step;
    return {status: "running", role: [label, spent(row.elapsed_s)].filter(Boolean).join(" ") || "进行中"};
  }
  const tr = currentTrace();
  const calls = (tr && tr.calls) || [];
  const seen = calls.some(call => call.name === name || (call.to || "").includes(name) || (call.target || "") === name)
    || ((tr && tr.choices) || "").includes(name);
  const last = lastDelegation(name);
  const bad = last && /FAIL|BLOCK/.test(last.status || "");
  if (bad) return {status: "fail", role: last.status};
  if (seen) return {status: "active", role: last && last.status ? last.status : "本轮"};
  if (last && last.status === "PASS") return {status: "pass", role: "通过 " + (spent(last.duration_s) || "")};
  if (last) return {status: "idle", role: last.status || "待命"};
  return {status: "idle", role: "待命"};
}

function moduleSeen(name) {
  const tr = currentTrace();
  if (!tr) return false;
  const calls = tr.calls || [];
  if (calls.some(call => (call.to || "").indexOf("module:" + name) >= 0 || (call.name || "").indexOf(name + "/") === 0)) return true;
  return (tr.route || "").split("→").some(part => part.trim() === name) || (tr.opened || []).some(path => String(path).indexOf(name + "/") === 0);
}

function renderArch() {
  const root = document.getElementById("arch");
  if (!root) return;
  root.replaceChildren();
  const tr = currentTrace();
  const unread = (state.board.thread || []).filter(msg => msg.role === "user" && msg.status !== "read").length;
  const liveN = (state.board.live || []).filter(row => !currentFeature() || row.feature === currentFeature()).length
    || ((state.board.current || {}).running || []).filter(row => row.agent && (!currentFeature() || row.feature === currentFeature())).length;
  const userStatus = unread || tr ? "active" : "idle";
  const conductorStatus = liveN ? "running" : (tr ? "active" : "idle");
  const inlet = el("div", {class: "lane"}, [
    el("h3", {}, [tx("入口")]),
    archNode("人", unread ? ("未读 " + unread) : ((tr && tr.trigger) || "待命"), userStatus),
    archNode("导体", (tr && tr.route) || (liveN ? "派工中" : "待命"), conductorStatus),
  ]);
  const skills = [];
  ((tr && tr.skills) || []).forEach(item => skills.push({name: item.name, role: item.why || tr.how || "调起"}));
  ((tr && tr.calls) || []).filter(call => call.kind === "skill").forEach(call => {
    if (!skills.some(item => item.name === call.name)) skills.push({name: call.name, role: [call.from, call.to, spent(call.duration_s)].filter(Boolean).join(" ")});
  });
  const skillLane = el("div", {class: "lane"}, [el("h3", {}, [tx("技能")])]);
  if (!skills.length) skillLane.append(archNode("技能", "没有记下", "idle"));
  skills.forEach(item => skillLane.append(archNode(item.name, item.role, tr ? "active" : "idle")));
  const agentLane = el("div", {class: "lane"}, [el("h3", {}, [tx("执行者")])]);
  let agentHot = false;
  let agentOn = false;
  AGENTS.forEach(([name, label]) => {
    const info = agentState(name);
    if (info.status === "running") agentHot = true;
    if (info.status === "active" || info.status === "running") agentOn = true;
    agentLane.append(archNode(label, name + " · " + info.role, info.status, () => {
      const live = (state.board.live || []).find(row => row.agent === name && row.feature === currentFeature());
      const last = lastDelegation(name);
      if (info.status === "running" && live) {
        state.liveKey = liveKey(live);
        state.delegKey = "";
      } else if (last) {
        state.delegKey = delegKey(last);
        state.liveKey = "";
      }
      render();
    }));
  });
  const modLane = el("div", {class: "lane"}, [el("h3", {}, [tx("模块")])]);
  let modOn = false;
  MODULES.forEach(([name, label]) => {
    const on = moduleSeen(name);
    if (on) modOn = true;
    modLane.append(archNode(label, name, on ? "active" : "idle"));
  });
  root.append(
    inlet,
    wire(liveN ? "hot" : (tr ? "on" : "idle")),
    skillLane,
    wire(agentHot ? "hot" : (agentOn ? "on" : "idle")),
    agentLane,
    wire(modOn ? "on" : "idle"),
    modLane,
  );
}

const STAGE_TRACK = [
  ["req-review", "需求评审"],
  ["req", "需求"],
  ["arch", "架构"],
  ["code", "编码"],
  ["test", "测试"],
  ["done", "完成"],
  ["ops", "排障"],
];

function stageTrack(stage) {
  const track = el("div", {class: "track"}, []);
  const idx = STAGE_TRACK.findIndex(item => item[0] === stage);
  STAGE_TRACK.forEach(([id, label], i) => {
    let cls = "";
    if (id === stage) cls = "on";
    else if (idx > i && stage !== "ops") cls = "was";
    else if (stage === "ops" && id !== "ops" && id !== "done") cls = "was";
    track.append(el("span", {class: cls}, [tx(label)]));
  });
  return track;
}

function taskCard(row, running) {
  const feature = row.feature || "未绑票";
  const title = row.intent || feature;
  const stageName = row.stage_label || row.stage || "未知";
  const stepBits = [row.workflow_id, row.label, row.step, row.kind, row.agent].filter(Boolean);
  if (row.shard) stepBits.push(row.shard);
  const paths = row.paths || [];
  const work = el("div", {class: "work"}, [
    el("div", {class: "now-k"}, [tx(row.agent ? "正在工作" : "当前步骤")]),
    el("div", {class: "now-title"}, [tx(row.agent || "未派执行者")]),
    el("div", {class: "now-meta"}, [tx([row.label, row.kind, row.mode ? ("方式 " + row.mode) : "", row.fencing ? ("围栏 " + row.fencing) : ""].filter(Boolean).join("  ·  "))]),
    el("div", {class: "now-meta"}, [tx((row.activity || []).length ? "回报还没记上。这一步刚写下：" : (paths.length ? "还没有回报。写入范围是下面这些文件。" : "还没有回报。"))]),
  ]);
  const activity = row.activity || [];
  if (activity.length) {
    activity.forEach(item => {
      work.append(el("div", {class: "now-meta"}, [tx(item.name + (item.tail ? "  " + item.tail : ""))]));
    });
  }
  if (paths.length) {
    const list = el("ul", {class: "paths"}, []);
    paths.forEach(path => list.append(el("li", {}, [tx(path)])));
    work.append(list);
  }
  const card = el("article", {class: "now-card" + (running ? " running" : "")}, [
    el("div", {}, [
      el("div", {class: "now-k"}, [tx(running ? "正在运行" : "没有正在跑的派工")]),
      el("div", {class: "now-title"}, [tx(title)]),
      el("div", {class: "now-meta"}, [tx(feature + (stepBits.length ? "  ·  " + stepBits.join("  ") : ""))]),
      running ? el("div", {class: "now-meta"}, [
        tx("已进行 "),
        el("span", {"data-elapsed": [row.feature, row.step, row.shard || ""].join("|")}, [tx(spent(row.elapsed_s))]),
      ]) : tx(""),
    ]),
    el("div", {class: "stage-chip"}, [tx("阶段"), el("b", {}, [tx(stageName)])]),
    stageTrack(row.stage),
    running ? work : tx(""),
  ]);
  return card;
}

function maxOf(rows, pick) {
  let max = 1;
  (rows || []).forEach(row => {
    const n = pick(row);
    if (n > max) max = n;
  });
  return max;
}

function pinBasis(text) {
  const box = document.getElementById("basis");
  if (box) box.value = text;
  const panel = document.getElementById("adjust");
  if (panel && panel.scrollIntoView) panel.scrollIntoView({block: "nearest"});
}

function instrument(kicker, children) {
  return el("div", {class: "meter"}, [el("div", {class: "meter-k"}, [tx(kicker)])].concat(children));
}

function hasTime(row) {
  return row.duration_s !== null && row.duration_s !== undefined && row.duration_s !== "";
}

function renderMeters() {
  const root = document.getElementById("meters");
  if (!root) return;
  const m = state.board.meters || {};
  const win = m.traces || 0;
  const scenarios = m.scenarios || [];
  const sceneMax = maxOf(scenarios, row => row.n || 0);
  const cols = el("div", {class: "cols"}, []);
  scenarios.forEach(row => {
    const n = row.n || 0;
    const button = el("button", {class: "col", type: "button", title: row.id + " " + n}, [
      el("i", {style: "height:" + (n ? Math.round(100 * n / sceneMax) : 0) + "%"}, []),
      el("b", {}, [tx(n ? String(n) : "")]),
      el("span", {}, [tx(String(row.id || "").replace(/^S/, ""))]),
    ]);
    button.addEventListener("click", () => pinBasis("窗口 " + win + " 轮 · 场景 " + row.id + " " + n + " 件"));
    cols.append(button);
  });
  const agents = m.agents || [];
  const timeMax = maxOf(agents, row => hasTime(row) ? Number(row.duration_s) : 0);
  const bars = el("div", {class: "hbars"}, []);
  agents.forEach(row => {
    const known = hasTime(row);
    const width = known ? Math.max(4, Math.round(100 * Number(row.duration_s) / timeMax)) : 0;
    const value = known ? spent(row.duration_s) : (row.untimed ? "未记时 " + row.untimed : "0");
    const button = el("button", {class: "hbar", type: "button"}, [
      el("span", {}, [tx(row.label || row.agent || "")]),
      el("u", {}, [el("i", {style: "width:" + width + "%"}, [])]),
      el("b", {}, [tx(value)]),
    ]);
    button.addEventListener("click", () => pinBasis("窗口 " + win + " 轮 · " + (row.label || "") + " " + (row.agent || "") + " · " + value + " · 委派 " + (row.n || 0) + " 件"));
    bars.append(button);
  });
  const reads = el("div", {class: "reads"}, []);
  (m.observation || []).forEach(row => {
    const button = el("button", {class: "read", type: "button"}, [
      el("b", {}, [tx((row.n || 0) + "/" + win)]),
      el("span", {}, [tx(row.label || row.id || "")]),
    ]);
    button.addEventListener("click", () => pinBasis("窗口 " + win + " 轮 · " + (row.label || row.id) + " " + (row.n || 0) + "/" + win));
    reads.append(button);
  });
  const pips = el("div", {class: "pips"}, []);
  (m.outcomes || []).concat(m.other_outcomes || []).forEach(row => {
    const button = el("button", {class: "pip", type: "button"}, [
      el("b", {}, [tx(String(row.n || 0))]),
      el("span", {}, [tx(row.id || "")]),
    ]);
    button.addEventListener("click", () => pinBasis("委派 " + (m.delegations || 0) + " 件 · " + row.id + " " + (row.n || 0)));
    pips.append(button);
  });
  if (m.missing_status) {
    pips.append(el("div", {class: "pip"}, [el("b", {}, [tx(String(m.missing_status))]), el("span", {}, [tx("未记状态")])]));
  }
  if (m.retries) {
    const button = el("button", {class: "pip", type: "button"}, [
      el("b", {}, [tx(String(m.retries))]),
      el("span", {}, [tx("重试")]),
    ]);
    button.addEventListener("click", () => pinBasis("委派重试 " + m.retries + " 件"));
    pips.append(button);
  }
  const hits = el("div", {class: "skill-hits"}, []);
  const skills = m.skills || [];
  if (!skills.length) hits.append(el("div", {class: "muted"}, [tx("没有记下")]));
  skills.forEach(row => {
    const button = el("button", {class: "skill-hit", type: "button"}, [
      el("span", {}, [tx(row.name || "")]),
      el("b", {}, [tx(String(row.n || 0))]),
    ]);
    button.addEventListener("click", () => pinBasis("技能 " + row.name + " · " + row.n + " 轮"));
    hits.append(button);
  });
  const hypos = el("div", {class: "reads"}, []);
  (m.hypotheses || []).concat(m.other_hypotheses || []).forEach(row => {
    const button = el("button", {class: "read", type: "button"}, [
      el("b", {}, [tx(String(row.n || 0))]),
      el("span", {}, [tx(row.label || row.id || "")]),
    ]);
    button.addEventListener("click", () => pinBasis("假设 · " + (row.label || row.id) + " " + (row.n || 0)));
    hypos.append(button);
  });
  root.replaceChildren(
    instrument("场景", [cols]),
    instrument("执行者耗时", [bars]),
    instrument("观察 " + win, [reads]),
    instrument("回报 " + (m.delegations || 0), [pips]),
    instrument("技能调起", [hits]),
    instrument("假设", [hypos]),
  );
}

function contextTarget() {
  const cur = state.board.current || {};
  const row = (cur.running && cur.running[0]) || cur.focus;
  if (!row) return currentFeature();
  return [row.feature, row.step, row.agent].filter(Boolean).join(" · ");
}

function renderAdjust() {
  const kinds = document.getElementById("kinds");
  const hint = document.getElementById("kind-hint");
  if (!kinds || !hint) return;
  kinds.replaceChildren();
  ADJUST.forEach(item => {
    const button = el("button", {class: "kind" + (state.kind === item[0] ? " on" : ""), type: "button"}, [tx(item[0])]);
    button.addEventListener("click", () => {
      state.kind = item[0];
      renderAdjust();
    });
    kinds.append(button);
  });
  const chosen = ADJUST.filter(item => item[0] === state.kind)[0] || ADJUST[0];
  hint.textContent = chosen[1];
  const target = document.getElementById("target");
  if (target && !state.targetDirty && document.activeElement !== target) target.value = contextTarget();
}

function renderNow() {
  const root = document.getElementById("now");
  if (!root) return;
  const cur = state.board.current || {running: [], focus: null};
  root.replaceChildren();
  const running = cur.running || [];
  if (running.length) {
    running.forEach(row => root.append(taskCard(row, true)));
    return;
  }
  if (cur.focus) {
    root.append(taskCard(cur.focus, false));
    return;
  }
  root.append(el("p", {class: "muted"}, [tx("没有正在运行的任务")]));
}

function render() {
  if (!state.traceName) {
    const cur = state.board.current || {};
    const feature = (cur.running && cur.running[0] && cur.running[0].feature) || (cur.focus && cur.focus.feature);
    const traces = state.board.traces || [];
    const match = feature && traces.find(item => item.feature === feature);
    const first = match || traces[0];
    if (first) state.traceName = first.name;
  }
  renderMeters();
  renderNow();
  renderArch();
  renderAdjust();
  renderTraces();
  renderTimeline();
  renderDetail();
  renderThread();
  paintHud();
}

function paintHud() {
  const named = [];
  (state.board.live || []).forEach(row => { if (row.agent) named.push(row.agent + "|" + row.step); });
  (((state.board.current || {}).running) || []).forEach(row => { if (row.agent) named.push(row.agent + "|" + row.step); });
  const n = new Set(named).size;
  const chip = document.getElementById("chip-live");
  const core = document.getElementById("core");
  if (chip) {
    chip.textContent = "LIVE " + n;
    chip.classList.toggle("hot", n > 0);
  }
  if (core) core.classList.toggle("hot", n > 0);
  const meters = state.board.meters || {};
  const win = document.getElementById("chip-window");
  const retry = document.getElementById("chip-retry");
  if (win) win.textContent = "WINDOW " + (meters.traces || 0);
  if (retry) {
    retry.textContent = "RETRY " + (meters.retries || 0);
    retry.classList.toggle("hot", (meters.retries || 0) > 0);
  }
  document.getElementById("fresh").textContent = "SYNC " + new Date().toLocaleTimeString();
}

function boardKey(board) {
  const copy = JSON.parse(JSON.stringify(board));
  (copy.live || []).forEach(row => { delete row.elapsed_s; });
  (((copy.current || {}).running) || []).forEach(row => { delete row.elapsed_s; });
  return JSON.stringify(copy);
}

function updateElapsed() {
  document.querySelectorAll("[data-elapsed]").forEach(node => {
    const key = node.getAttribute("data-elapsed");
    const pools = [(state.board.live || []), ((state.board.current || {}).running || [])];
    const row = pools.map(pool => pool.find(item => liveKey(item) === key)).find(Boolean);
    if (row) node.textContent = spent(row.elapsed_s);
  });
  paintHud();
}

async function refresh() {
  const res = await fetch("/api/board", {cache: "no-store"});
  if (!res.ok) throw new Error("board " + res.status);
  const data = await res.json();
  const key = boardKey(data);
  state.board = data;
  if (key !== lastKey) {
    lastKey = key;
    render();
  } else {
    updateElapsed();
  }
}

document.getElementById("target").addEventListener("input", () => { state.targetDirty = true; });

document.getElementById("adjust-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const opinion = document.getElementById("opinion").value.trim();
  const err = document.getElementById("err");
  err.textContent = "";
  if (!opinion) {
    err.textContent = "写一句意见";
    return;
  }
  const target = document.getElementById("target").value.trim();
  const basis = document.getElementById("basis").value.trim();
  const lines = ["[调整] " + state.kind];
  if (target) lines.push("目标: " + target);
  if (basis) lines.push("依据: " + basis);
  lines.push("意见: " + opinion);
  const res = await fetch("/api/thread", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text: lines.join("\\n")}),
  });
  if (!res.ok) {
    err.textContent = "没发出去";
    return;
  }
  document.getElementById("opinion").value = "";
  document.getElementById("basis").value = "";
  await refresh();
});

document.getElementById("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const box = document.getElementById("text");
  const text = box.value.trim();
  const err = document.getElementById("err");
  err.textContent = "";
  if (!text) return;
  const res = await fetch("/api/thread", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text}),
  });
  if (!res.ok) {
    err.textContent = "没发出去";
    return;
  }
  box.value = "";
  await refresh();
});

refresh().catch(err => { document.getElementById("err").textContent = String(err); });
setInterval(() => refresh().catch(() => {}), 2000);
</script>
</body>
</html>
"""


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def opt_duration(value: object) -> int | None:
    """A recorded duration. Missing stays missing; zero is a real zero."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def elapsed(started: str) -> int | None:
    if not started:
        return None
    try:
        begin = dt.datetime.fromisoformat(started)
    except ValueError:
        return None
    if begin.tzinfo is None:
        begin = begin.astimezone()
    return max(0, int((dt.datetime.now().astimezone() - begin).total_seconds()))


def check_token(value: str, label: str) -> str:
    text = (value or "").strip()
    if not text or text in (".", "..") or "/" in text or "\\" in text or ".." in text:
        raise SystemExit(f"FAIL {label} invalid")
    if len(text) > 120:
        raise SystemExit(f"FAIL {label} too long")
    return text


def thread_path(folder: Path) -> Path:
    return folder / "thread.yaml"


def live_path(folder: Path) -> Path:
    return folder / "live.yaml"


def _messages(data: dict) -> list:
    items = data.get("messages")
    return items if isinstance(items, list) else []


def _running(data: dict) -> list:
    items = data.get("running")
    return items if isinstance(items, list) else []


def read_thread(folder: Path) -> list[dict]:
    data = safeyaml.mapping(thread_path(folder)) or {}
    return [item for item in _messages(data) if isinstance(item, dict)]


def unread(folder: Path) -> list[dict]:
    return [item for item in read_thread(folder) if item.get("role") == "user" and item.get("status") != "read"]


def _next_id(messages: list) -> int:
    ids = []
    for item in messages:
        if isinstance(item, dict):
            ids.append(safeyaml.as_int(item.get("id"), 0))
    return max(ids, default=0) + 1


def _message(messages: list, role: str, text: str, status: str) -> dict:
    return {
        "id": _next_id(messages),
        "at": now(),
        "role": role,
        "text": text,
        "status": status,
    }


def post(folder: Path, text: str, role: str = "user") -> dict:
    body = (text or "").strip()
    if not body:
        raise SystemExit("FAIL text empty")
    if len(body) > TEXT_LIMIT:
        raise SystemExit("FAIL text too long")
    if role not in ("user", "conductor"):
        raise SystemExit("FAIL role invalid")
    holder: dict = {}

    def mutate(data: dict) -> dict:
        data["schema_version"] = 1
        messages = _messages(data)
        data["messages"] = messages
        msg = _message(messages, role, body, "unread" if role == "user" else "read")
        messages.append(msg)
        holder["msg"] = msg
        return data

    safeyaml.save_locked(thread_path(folder), mutate)
    return holder["msg"]


def reply(folder: Path, text: str) -> dict:
    body = (text or "").strip()
    if not body:
        raise SystemExit("FAIL text empty")
    if len(body) > TEXT_LIMIT:
        raise SystemExit("FAIL text too long")
    holder: dict = {}

    def mutate(data: dict) -> dict:
        data["schema_version"] = 1
        messages = _messages(data)
        data["messages"] = messages
        for item in messages:
            if isinstance(item, dict) and item.get("role") == "user" and item.get("status") != "read":
                item["status"] = "read"
        msg = _message(messages, "conductor", body, "read")
        messages.append(msg)
        holder["msg"] = msg
        return data

    safeyaml.save_locked(thread_path(folder), mutate)
    return holder["msg"]


def read_live(folder: Path) -> list[dict]:
    data = safeyaml.mapping(live_path(folder)) or {}
    out = []
    for item in _running(data):
        if not isinstance(item, dict):
            continue
        started = str(item.get("started_at") or "")
        out.append({
            "feature": str(item.get("feature") or ""),
            "step": str(item.get("step") or ""),
            "shard": str(item.get("shard") or ""),
            "agent": str(item.get("agent") or ""),
            "kind": str(item.get("kind") or ""),
            "started_at": started,
            "elapsed_s": elapsed(started),
        })
    return out


def live_add(folder: Path, *, feature: str, step: str, agent: str, shard: str = "", kind: str = "") -> dict:
    feature = check_token(feature, "feature")
    step = check_token(step, "step")
    agent = check_token(agent, "agent")
    shard = check_token(shard, "shard") if shard else ""
    kind = (kind or "").strip()
    holder: dict = {}

    def mutate(data: dict) -> dict:
        data["schema_version"] = 1
        rows = [
            row for row in _running(data)
            if not (
                isinstance(row, dict)
                and str(row.get("feature") or "") == feature
                and str(row.get("step") or "") == step
                and str(row.get("shard") or "") == shard
            )
        ]
        row = {
            "feature": feature,
            "step": step,
            "shard": shard,
            "agent": agent,
            "kind": kind,
            "started_at": now(),
        }
        rows.append(row)
        data["running"] = rows
        holder["row"] = row
        return data

    safeyaml.save_locked(live_path(folder), mutate)
    return holder["row"]


def live_clear(folder: Path, *, feature: str, step: str, shard: str | None = None) -> int:
    feature = check_token(feature, "feature")
    step = check_token(step, "step")
    if shard is not None and shard != "":
        shard = check_token(shard, "shard")
    holder = {"n": 0}

    def mutate(data: dict) -> dict:
        data["schema_version"] = 1
        kept = []
        removed = 0
        for row in _running(data):
            if not isinstance(row, dict):
                continue
            same = str(row.get("feature") or "") == feature and str(row.get("step") or "") == step
            if shard is not None:
                same = same and str(row.get("shard") or "") == shard
            if same:
                removed += 1
                continue
            kept.append(row)
        data["running"] = kept
        holder["n"] = removed
        return data

    safeyaml.save_locked(live_path(folder), mutate)
    return holder["n"]


def jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return str(value)


def _trace_view(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        print(f"WARN unreadable trace, skipped: {path}", file=sys.stderr)
        return None
    data = safeyaml.mapping_from_text(text)
    if not data:
        print(f"WARN unreadable or not a mapping, skipped: {path}", file=sys.stderr)
        return None
    seg = trace.path_segments(text)
    invoke = data.get("invoke") if isinstance(data.get("invoke"), dict) else {}
    skills = []
    for item in invoke.get("skills") or []:
        if isinstance(item, dict) and item.get("name"):
            skills.append({
                "name": str(item.get("name")),
                "why": str(item.get("why") or ""),
                "path": str(item.get("path") or ""),
            })
    calls = []
    for item in data.get("calls") or []:
        if not isinstance(item, dict):
            continue
        calls.append({
            "kind": str(item.get("kind") or ""),
            "name": str(item.get("name") or ""),
            "from": str(item.get("from") or ""),
            "to": str(item.get("to") or ""),
            "thinking": str(item.get("thinking") or ""),
            "why": str(item.get("why") or ""),
            "duration_s": opt_duration(item.get("duration_s")),
            "result": str(item.get("result") or ""),
        })
    opened = data.get("opened") if isinstance(data.get("opened"), list) else []
    thinking = data.get("thinking") if isinstance(data.get("thinking"), dict) else {}
    route = data.get("route") if isinstance(data.get("route"), dict) else {}
    return {
        "name": path.name,
        "at": str(data.get("at") or ""),
        "feature": str(data.get("feature") or "-"),
        "intent": str(data.get("intent") or ""),
        "stage": str(route.get("stage") or "") if isinstance(route, dict) else "",
        "scenario": str(route.get("scenario") or "") if isinstance(route, dict) else "",
        "how": str(invoke.get("how") or ""),
        "trigger": str(invoke.get("trigger") or seg.get("trigger") or ""),
        "route": seg.get("route") or "",
        "why": seg.get("why") or "",
        "skills_line": seg.get("skills") or "",
        "hops": seg.get("hops") or "",
        "react": seg.get("react") or "",
        "opened_line": seg.get("opened") or "",
        "stop": str(data.get("stop") or seg.get("stop") or ""),
        "next": str(data.get("next") or seg.get("next") or ""),
        "choices": seg.get("choices") or "",
        "skills": skills,
        "calls": calls,
        "opened": [str(item) for item in opened],
        "thinking": str(thinking.get("summary") or ""),
    }


def _delegation_view(record: dict) -> dict:
    return {
        "step": str(record.get("step") or ""),
        "kind": str(record.get("kind") or ""),
        "agent": str(record.get("agent") or ""),
        "attempt": safeyaml.as_int(record.get("attempt"), 1),
        "shard": str(record.get("shard") or ""),
        "status": delegation.report_status(record),
        "duration_s": delegation.duration_of(record),
        "evidence": delegation.report_evidence(record),
        "started_at": str(record.get("started_at") or ""),
        "finished_at": str(record.get("finished_at") or ""),
        "checks": jsonable(record.get("checks") or {}),
        "suggest": str(record.get("suggest") or ""),
        "brief": jsonable(record.get("brief") or {}),
        "report": jsonable(record.get("report") or {}),
        "outcome": str(record.get("outcome") or ""),
    }


def _hypotheses(feature: str, repo: Path) -> list[dict]:
    if not feature or feature == "-":
        return []
    data = hypothesis.load(hypothesis.ledger_path(feature, repo), feature)
    out = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        out.append({
            "id": str(item.get("id") or ""),
            "claim": str(item.get("claim") or ""),
            "status": str(item.get("status") or ""),
            "at": str(item.get("at") or ""),
        })
    return out


def _run_view(feature: str, repo: Path, live: list[dict]) -> dict:
    run = delegation.load_run(feature, repo) or {}
    steps = []
    for step in run.get("steps") or []:
        if not isinstance(step, dict):
            continue
        sid = str(step.get("id") or "")
        status = str(step.get("status") or "pending")
        delegated = step.get("delegated") if isinstance(step.get("delegated"), dict) else {}
        lease = step.get("lease") if isinstance(step.get("lease"), dict) else {}
        scope = step.get("with") if isinstance(step.get("with"), dict) else {}
        paths = [str(item) for item in lease.get("paths") or [] if str(item).strip()]
        held = bool(lease.get("id")) and not lease.get("released_at")
        running = status == "pending" and (
            held or any(item["feature"] == feature and item["step"] == sid for item in live)
        )
        fencing = lease.get("fencing")
        steps.append({
            "id": sid,
            "kind": str(step.get("kind") or ""),
            "label": str(step.get("label") or ""),
            "status": status,
            "agent": str(delegated.get("agent") or ""),
            "started_at": str(delegated.get("at") or ""),
            "paths": paths,
            "fencing": fencing if isinstance(fencing, int) else None,
            "held": held,
            "mode": str(scope.get("mode") or ""),
            "running": running,
        })
    return {
        "workflow_id": str(run.get("workflow_id") or ""),
        "status": str(run.get("status") or ""),
        "steps": steps,
    }


def _feature_view(feature: str, repo: Path, live: list[dict]) -> dict:
    if not feature or feature == "-":
        delegations = []
    else:
        delegations = [_delegation_view(record) for _, record in delegation.load_all(feature, repo)]
        delegations.sort(key=lambda row: (row["step"], row["attempt"], row["shard"]))
    ops = [row["duration_s"] for row in delegations if row["agent"] == "idev-ops" and row["duration_s"] is not None]
    return {
        "run": _run_view(feature, repo, live) if feature and feature != "-" else {"workflow_id": "", "status": "", "steps": []},
        "delegations": delegations,
        "hypotheses": _hypotheses(feature, repo),
        "ops_duration_s": sum(ops) if ops else None,
    }


STAGE_LABELS = {
    "req-review": "需求评审",
    "req": "需求",
    "arch": "架构",
    "code": "编码",
    "test": "测试",
    "done": "完成",
    "ops": "排障",
    "verify-plan": "测试计划",
}
STEP_DONE = {"PASS", "SKIPPED", "UNPROVEN", "AUTO"}


def _stage_of(feature: str, repo: Path, traces: list[dict]) -> tuple[str, str]:
    raw = ""
    if feature and feature != "-":
        data = safeyaml.mapping(delegation.home(feature, repo) / "deliver.yaml") or {}
        raw = str(data.get("stage") or "").strip()
    if not raw:
        for item in traces:
            if item.get("feature") == feature and item.get("stage"):
                raw = str(item["stage"])
                break
    return raw, STAGE_LABELS.get(raw, raw)


_SECRET_LINE = __import__("re").compile(r"(?i)(token|secret|password|cipher)")


def _tail_line(path: Path, limit: int = 160) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - 2048))
            raw = handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return ""
    text = lines[-1]
    if _SECRET_LINE.search(text):
        return "(已略过)"
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _step_activity(feature: str, repo: Path, started_at: str, limit: int = 8) -> list[dict]:
    """Logs written after this step was delegated. The run file often lags them."""
    if not feature or feature == "-":
        return []
    start = None
    if started_at:
        try:
            start = dt.datetime.fromisoformat(started_at)
        except ValueError:
            start = None
        if start is not None and start.tzinfo is None:
            start = start.astimezone()
    if start is None:
        return []
    logs = delegation.home(feature, repo) / "workflow" / "logs"
    if not logs.is_dir():
        return []
    found: list[tuple[float, Path]] = []
    cutoff = start.timestamp() - 1
    for path in logs.glob("*.log"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            found.append((mtime, path))
    found.sort(key=lambda item: item[0], reverse=True)
    out = []
    for mtime, path in found[:limit]:
        out.append({
            "name": path.name,
            "at": dt.datetime.fromtimestamp(mtime).astimezone().isoformat(timespec="seconds"),
            "tail": _tail_line(path),
        })
    return out


def _elapsed_since(started_at: str) -> int | None:
    if not started_at:
        return None
    try:
        start = dt.datetime.fromisoformat(started_at)
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.astimezone()
    seconds = int((dt.datetime.now().astimezone() - start).total_seconds())
    return seconds if seconds >= 0 else None


def _running_features(repo: Path) -> list[str]:
    """Tickets whose workflow run.yaml is still running, whether or not a trace names them."""
    names: list[str] = []
    for base in (repo / "docs" / "task", repo / ".idev" / "task"):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            data = safeyaml.mapping(child / "workflow" / "run.yaml") or {}
            if str(data.get("status") or "") != "running":
                continue
            feature = str(data.get("feature") or child.name)
            if feature and feature not in names:
                names.append(feature)
    return names


def _open_step(steps: list[dict]) -> dict | None:
    for step in steps:
        if str(step.get("status") or "pending") not in STEP_DONE:
            return step
    return None


def _focus(feature: str, traces: list[dict], features: dict, repo: Path) -> dict:
    pack = features.get(feature) or {}
    run = pack.get("run") or {}
    stage, label = _stage_of(feature, repo, traces)
    intent = next((item["intent"] for item in traces if item.get("feature") == feature and item.get("intent")), "")
    step = _open_step(run.get("steps") or []) or {}
    return {
        "feature": feature,
        "intent": intent,
        "stage": stage,
        "stage_label": label,
        "workflow_id": run.get("workflow_id") or "",
        "run_status": run.get("status") or "",
        "step": step.get("id") or "",
        "kind": step.get("kind") or "",
        "label": step.get("label") or "",
        "agent": step.get("agent") or "",
        "shard": "",
        "step_status": step.get("status") or "",
        "started_at": step.get("started_at") or "",
        "paths": step.get("paths") or [],
        "fencing": step.get("fencing"),
        "held": bool(step.get("held")),
        "mode": step.get("mode") or "",
    }


def _current(traces: list[dict], features: dict, live: list[dict], repo: Path) -> dict:
    running = []
    for item in live:
        feature = item.get("feature") or ""
        focus = _focus(feature, traces, features, repo) if feature and feature != "-" else {}
        steps = (((features.get(feature) or {}).get("run") or {}).get("steps") or [])
        step = next((one for one in steps if one.get("id") == item.get("step")), {})
        running.append({
            "feature": feature,
            "intent": focus.get("intent") or "",
            "stage": focus.get("stage") or "",
            "stage_label": focus.get("stage_label") or "",
            "workflow_id": focus.get("workflow_id") or "",
            "run_status": focus.get("run_status") or "",
            "step": item.get("step") or "",
            "kind": item.get("kind") or focus.get("kind") or "",
            "label": focus.get("label") or "",
            "agent": item.get("agent") or "",
            "shard": item.get("shard") or "",
            "started_at": item.get("started_at") or "",
            "elapsed_s": item.get("elapsed_s"),
            "paths": step.get("paths") or [],
            "fencing": step.get("fencing"),
            "held": bool(step.get("held")),
            "mode": step.get("mode") or "",
            "activity": _step_activity(feature, repo, str(item.get("started_at") or "")),
        })
    covered = {(row["feature"], row["step"]) for row in running}
    for feature, pack in features.items():
        run = pack.get("run") or {}
        if run.get("status") != "running":
            continue
        step = _open_step(run.get("steps") or []) or {}
        key = (feature, step.get("id") or "")
        if not step or key in covered:
            continue
        focus = _focus(feature, traces, features, repo)
        started = step.get("started_at") or ""
        running.append({
            "feature": feature,
            "intent": focus.get("intent") or "",
            "stage": focus.get("stage") or "",
            "stage_label": focus.get("stage_label") or "",
            "workflow_id": run.get("workflow_id") or "",
            "run_status": "running",
            "step": step.get("id") or "",
            "kind": step.get("kind") or "",
            "label": step.get("label") or "",
            "agent": step.get("agent") or "",
            "shard": "",
            "started_at": started,
            "elapsed_s": _elapsed_since(started),
            "paths": step.get("paths") or [],
            "fencing": step.get("fencing"),
            "held": bool(step.get("held")),
            "mode": step.get("mode") or "",
            "activity": _step_activity(feature, repo, started),
        })
        covered.add(key)
    if running and running[0]["feature"] not in ("", "-"):
        feature = running[0]["feature"]
    else:
        feature = next((item["feature"] for item in traces if item.get("feature") not in ("", "-")), "")
    focus = _focus(feature, traces, features, repo) if feature else None
    return {"running": running, "focus": focus}


SCENARIOS = tuple(f"S{i}" for i in range(1, 9))
AGENT_LABELS = {
    "idev-deliver": "交付",
    "idev-coder": "编码",
    "idev-reviewer": "审查",
    "idev-verifier": "验证",
    "idev-ops": "排障",
}
OUTCOMES = ("PASS", "FAIL", "BLOCKED", "UNPROVEN")
HYPO_STATUS = (("open", "待验"), ("proven", "已证成"), ("disproven", "已排除"))


def _scenario_of(item: dict) -> str:
    raw = str(item.get("scenario") or "").strip()
    if raw in SCENARIOS:
        return raw
    head = str(item.get("route") or "").split("→", 1)[0].strip()
    return head if head in SCENARIOS else ""


def _skill_names(item: dict) -> list[str]:
    names: list[str] = []
    for skill in item.get("skills") or []:
        name = str(skill.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    if names:
        return names
    for call in item.get("calls") or []:
        if str(call.get("kind") or "") != "skill":
            continue
        name = str(call.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _saw(item: dict, kind: str) -> bool:
    calls = [call for call in (item.get("calls") or []) if isinstance(call, dict)]
    choices = str(item.get("choices") or "")
    if kind == "skill":
        return bool(item.get("skills")) or bool(item.get("how")) or any(str(call.get("kind") or "") == "skill" for call in calls)
    if kind == "delegate":
        return "delegate→" in choices or any(str(call.get("kind") or "") == "agent" for call in calls)
    if kind == "model":
        return "model→" in choices or any(str(call.get("kind") or "") == "model" for call in calls)
    if kind == "hop":
        return any(str(call.get("from") or "") and str(call.get("to") or "") for call in calls)
    return False


def _meters(traces: list[dict], features: dict, live: list[dict]) -> dict:
    """Counts over the trace window and the tickets on this board. Not a score."""
    scenario_n = {sid: 0 for sid in SCENARIOS}
    obs = {"skill": 0, "delegate": 0, "model": 0, "hop": 0}
    skills: dict[str, int] = {}
    for item in traces:
        sid = _scenario_of(item)
        if sid:
            scenario_n[sid] += 1
        for key in obs:
            if _saw(item, key):
                obs[key] += 1
        for name in _skill_names(item):
            skills[name] = skills.get(name, 0) + 1
    agent_n: dict[str, dict] = {}
    outcome_n = {sid: 0 for sid in OUTCOMES}
    other: dict[str, int] = {}
    missing_status = 0
    retries = 0
    delegations = 0
    for pack in features.values():
        for row in pack.get("delegations") or []:
            delegations += 1
            agent = str(row.get("agent") or "")
            if agent:
                slot = agent_n.setdefault(agent, {"n": 0, "duration_s": 0, "timed": 0, "untimed": 0})
                slot["n"] += 1
                if row.get("duration_s") is None:
                    slot["untimed"] += 1
                else:
                    slot["timed"] += 1
                    slot["duration_s"] += int(row["duration_s"])
            status = str(row.get("status") or "")
            if not status:
                missing_status += 1
            elif status in outcome_n:
                outcome_n[status] += 1
            else:
                other[status] = other.get(status, 0) + 1
            if safeyaml.as_int(row.get("attempt"), 1) > 1:
                retries += 1
    hypo_n = {sid: 0 for sid, _label in HYPO_STATUS}
    other_h: dict[str, int] = {}
    for pack in features.values():
        for item in pack.get("hypotheses") or []:
            status = str(item.get("status") or "open")
            if status in hypo_n:
                hypo_n[status] += 1
            else:
                other_h[status] = other_h.get(status, 0) + 1
    agents = []
    for name in list(AGENT_LABELS) + [name for name in agent_n if name not in AGENT_LABELS]:
        slot = agent_n.get(name) or {"n": 0, "duration_s": 0, "timed": 0, "untimed": 0}
        agents.append({
            "agent": name,
            "label": AGENT_LABELS.get(name, name),
            "n": slot["n"],
            "duration_s": slot["duration_s"] if slot["timed"] else None,
            "untimed": slot["untimed"],
        })
    skill_rows = [{"name": name, "n": count} for name, count in skills.items()]
    skill_rows.sort(key=lambda row: (-row["n"], row["name"]))
    return {
        "traces": len(traces),
        "scenarios": [{"id": sid, "n": scenario_n[sid]} for sid in SCENARIOS],
        "observation": [
            {"id": "skill", "label": "技能", "n": obs["skill"]},
            {"id": "delegate", "label": "委派", "n": obs["delegate"]},
            {"id": "model", "label": "模型", "n": obs["model"]},
            {"id": "hop", "label": "跳转", "n": obs["hop"]},
        ],
        "agents": agents,
        "outcomes": [{"id": sid, "n": outcome_n[sid]} for sid in OUTCOMES],
        "other_outcomes": [{"id": sid, "n": other[sid]} for sid in sorted(other)],
        "missing_status": missing_status,
        "retries": retries,
        "delegations": delegations,
        "skills": skill_rows[:8],
        "hypotheses": [{"id": sid, "label": label, "n": hypo_n[sid]} for sid, label in HYPO_STATUS],
        "other_hypotheses": [{"id": sid, "n": other_h[sid]} for sid in sorted(other_h)],
        "live": len(live),
    }


def board(*, trace_dir: Path, repo: Path, console_dir: Path) -> dict:
    files = trace.listed_traces(trace_dir)[-TRACE_LIMIT:]
    traces = []
    for path in reversed(files):
        item = _trace_view(path)
        if item is not None:
            traces.append(item)
    live = read_live(console_dir)
    features: list[str] = []
    for item in traces:
        if item["feature"] not in features:
            features.append(item["feature"])
    for item in live:
        if item["feature"] and item["feature"] not in features:
            features.append(item["feature"])
    for name in _running_features(repo):
        if name not in features:
            features.append(name)
    viewed = {name: _feature_view(name, repo, live) for name in features}
    return {
        "traces": traces,
        "features": viewed,
        "live": live,
        "current": _current(traces, viewed, live, repo),
        "meters": _meters(traces, viewed, live),
        "thread": read_thread(console_dir),
    }


class ConsoleHandler(BaseHTTPRequestHandler):
    trace_dir: Path
    repo: Path
    console_dir: Path

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send(self, code: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, payload: object) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
            return
        if path == "/api/board":
            self._json(200, board(trace_dir=self.trace_dir, repo=self.repo, console_dir=self.console_dir))
            return
        if path == "/api/thread":
            self._json(200, {"messages": read_thread(self.console_dir)})
            return
        self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/thread":
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        length = safeyaml.as_int(self.headers.get("Content-Length"), 0)
        if length <= 0 or length > BODY_LIMIT:
            self._json(400, {"ok": False, "error": "body"})
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "json"})
            return
        text = payload.get("text") if isinstance(payload, dict) else ""
        try:
            msg = post(self.console_dir, str(text or ""))
        except SystemExit:
            self._json(400, {"ok": False, "error": "text"})
            return
        self._json(200, {"ok": True, "message": msg})


def make_server(trace_dir: Path, repo: Path, console_dir: Path, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    console_dir.mkdir(parents=True, exist_ok=True)

    class Bound(ConsoleHandler):
        pass

    Bound.trace_dir = trace_dir
    Bound.repo = repo
    Bound.console_dir = console_dir
    return ThreadingHTTPServer((HOST, port), Bound)


def serve(trace_dir: Path, repo: Path, console_dir: Path, port: int, open_browser: bool) -> int:
    try:
        httpd = make_server(trace_dir, repo, console_dir, port)
    except OSError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    url = f"http://{HOST}:{httpd.server_address[1]}/"
    print(f"console {url}", flush=True)
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


def _print_pending(folder: Path) -> int:
    items = unread(folder)
    print(f"pending: {len(items)}")
    for item in items:
        print("---")
        print(f"id: {item.get('id')}")
        print(f"at: {item.get('at')}")
        print("text: |")
        for line in str(item.get("text") or "").splitlines() or [""]:
            print(f"  {line}")
    return 0


def _dir(value: Path | None, kind: str, *, mkdir: bool) -> Path:
    if value is None:
        if kind == "console":
            return sink_dir("console", mkdir=mkdir)
        if kind == "traces":
            return trace.default_dir()
        repo = product_repo()
        return repo if repo is not None else Path.cwd().resolve()
    path = value.expanduser().resolve()
    if mkdir:
        path.mkdir(parents=True, exist_ok=True)
    return path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    known = {"serve", "pending", "reply", "live", "board"}
    if not argv or argv[0] not in known:
        argv = ["serve", *argv]

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_dirs(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--console-dir", type=Path)
        cmd.add_argument("--trace-dir", type=Path)
        cmd.add_argument("--repo", type=Path)

    serve_cmd = sub.add_parser("serve", help="open the page")
    add_dirs(serve_cmd)
    serve_cmd.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_cmd.add_argument("--no-open", action="store_true")

    pending_cmd = sub.add_parser("pending", help="print unread user messages")
    add_dirs(pending_cmd)

    reply_cmd = sub.add_parser("reply", help="append a conductor reply and mark user messages read")
    add_dirs(reply_cmd)
    reply_cmd.add_argument("--text", required=True)

    live_cmd = sub.add_parser("live", help="mark an agent running or clear it")
    add_dirs(live_cmd)
    mode = live_cmd.add_mutually_exclusive_group(required=True)
    mode.add_argument("--add", action="store_true")
    mode.add_argument("--clear", action="store_true")
    live_cmd.add_argument("--feature", required=True)
    live_cmd.add_argument("--step", required=True)
    live_cmd.add_argument("--agent", default="")
    live_cmd.add_argument("--shard", default=None)
    live_cmd.add_argument("--kind", default="")

    board_cmd = sub.add_parser("board", help="print the board json")
    add_dirs(board_cmd)

    args = parser.parse_args(argv)
    mkdir = args.cmd in ("serve", "reply", "live")
    chosen = args.repo.expanduser().resolve() if args.repo else None

    def bound(flag: Path | None, kind: str) -> Path:
        if flag is not None:
            return _dir(flag, kind, mkdir=mkdir and kind == "console")
        if chosen is not None and kind in ("console", "traces"):
            return sink_dir(kind, mkdir=mkdir and kind == "console", start=chosen)
        return _dir(None, kind, mkdir=mkdir and kind == "console")

    folder = bound(args.console_dir, "console")
    if args.cmd == "pending":
        return _print_pending(folder)
    if args.cmd == "reply":
        msg = reply(folder, args.text)
        print(f"reply id={msg['id']}")
        return 0
    if args.cmd == "live":
        if args.add:
            if not args.agent:
                print("FAIL --agent is required with --add", file=sys.stderr)
                return 2
            row = live_add(
                folder,
                feature=args.feature,
                step=args.step,
                agent=args.agent,
                shard=args.shard or "",
                kind=args.kind,
            )
            label = row["step"] if not row["shard"] else f"{row['step']}/{row['shard']}"
            print(f"live add {row['feature']} {label} {row['agent']}")
            return 0
        shard = None if args.shard is None else args.shard
        removed = live_clear(folder, feature=args.feature, step=args.step, shard=shard)
        print(f"live clear {args.feature} {args.step} {removed}")
        return 0
    traces = bound(args.trace_dir, "traces")
    repo = _dir(args.repo, "repo", mkdir=False)
    if args.cmd == "board":
        print(json.dumps(board(trace_dir=traces, repo=repo, console_dir=folder), ensure_ascii=False, indent=2))
        return 0
    return serve(traces, repo, folder, args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    sys.exit(main())
