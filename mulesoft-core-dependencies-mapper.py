#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Varredura do repositório Maven local (~/.m2/**) capturando artefatos MuleSoft
e gerando um grafo de dependências. O PNG é salvo na pasta atual, a menos que
você especifique --out <arquivo>.

Autor : Leonel Dorneles Porto
E-mail: leonel.d.porto@accenture.com
"""

from __future__ import annotations
import argparse, importlib, subprocess, sys, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Callable

# ────────────────────── instalação "preguiçosa" ──────────────────────
def ensure(mod_path: str):
    try:
        return importlib.import_module(mod_path)
    except ModuleNotFoundError:
        root = mod_path.split(".")[0]
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", root])
        return importlib.import_module(mod_path)

nx  = ensure("networkx")              # type: ignore
plt = ensure("matplotlib.pyplot")     # type: ignore
ensure("scipy")                       # spring_layout
colorama = ensure("colorama")         # cores cross-platform
colorama.just_fix_windows_console()

# ─────────────────────────── logger bonito ───────────────────────────
ICON = {"info": "ℹ️", "ok": "✅", "warn": "⚠️", "err": "❌", "setup": "🔧"}
CLR  = {
    "cyan":  colorama.Fore.CYAN,
    "green": colorama.Fore.GREEN,
    "yellow":colorama.Fore.YELLOW,
    "red":   colorama.Fore.RED,
    "reset": colorama.Style.RESET_ALL,
}

def log(msg: str, level: str = "info", color: str = "cyan") -> None:
    print(f"{CLR[color]}{ICON[level]} {msg}{CLR['reset']}")

# ────────────────────────── constantes/helpers ───────────────────────
FILTER_PREFIXES = ("org.mule", "com.mulesoft")
NS              = {"m": "http://maven.apache.org/POM/4.0.0"}
GRAPH           = nx.DiGraph()

def _text(tag: Optional[ET.Element]) -> Optional[str]:
    return tag.text.strip() if tag is not None and tag.text else None

def _is_mule(group_id: str | None) -> bool:
    return bool(group_id) and group_id.startswith(FILTER_PREFIXES)

# ───────────────────────────── parser de POM ─────────────────────────
def extract_gav(root: ET.Element) -> Optional[str]:
    gid = _text(root.find("m:groupId", NS))
    aid = _text(root.find("m:artifactId", NS))
    ver = _text(root.find("m:version", NS))
    parent = root.find("m:parent", NS)
    if parent is not None:
        gid = gid or _text(parent.find("m:groupId", NS))
        ver = ver or _text(parent.find("m:version", NS))
    if not _is_mule(gid):
        return None
    return f"{gid}:{aid}:{ver}" if gid and aid and ver else None

def extract_dependencies(root: ET.Element) -> List[str]:
    deps_list: List[str] = []
    deps = root.find("m:dependencies", NS)
    if deps is None:
        return deps_list
    for dep in deps.findall("m:dependency", NS):
        gid = _text(dep.find("m:groupId", NS))
        if not _is_mule(gid):
            continue
        aid = _text(dep.find("m:artifactId", NS))
        ver = _text(dep.find("m:version", NS))
        if gid and aid and ver:
            deps_list.append(f"{gid}:{aid}:{ver}")
    return deps_list

def add_pom(pom_content: str) -> bool:
    try:
        root = ET.fromstring(pom_content)
    except ET.ParseError:
        return False
    gav = extract_gav(root)
    if not gav:
        return False
    GRAPH.add_node(gav)
    for dep in extract_dependencies(root):
        GRAPH.add_edge(gav, dep)
    return True

# ────────────────────────── varredura do m2 ──────────────────────────
def scan_m2(base: Path, max_mule_poms: int = 10) -> None:
    loaded = 0
    for pom in base.rglob("pom.xml"):
        if loaded >= max_mule_poms:
            break
        try:
            if add_pom(pom.read_text(encoding="utf-8")):
                loaded += 1
        except Exception:
            continue

    if loaded < max_mule_poms:
        for jar in base.rglob("*.jar"):
            if loaded >= max_mule_poms:
                break
            try:
                with zipfile.ZipFile(jar) as z:
                    for entry in z.infolist():
                        if entry.filename.endswith("pom.xml") and "META-INF/maven/" in entry.filename:
                            if add_pom(z.read(entry.filename).decode("utf-8")):
                                loaded += 1
                            break
            except Exception:
                continue

# ─────────────────────────── visualização ───────────────────────────
def draw_graph(graph: "nx.DiGraph", outfile: Path) -> None:
    if graph.number_of_nodes() == 0:
        log("Nenhuma dependência MuleSoft encontrada – grafo vazio.", "warn", "yellow")
        return
    plt.figure(figsize=(14, 14))
    pos = nx.spring_layout(graph, k=0.4, seed=42)
    nx.draw(
        graph, pos, with_labels=True, node_size=800,
        node_color="#89CFF0", font_size=6, arrows=True,
    )
    plt.title("Dependências MuleSoft (amostragem)")
    plt.savefig(outfile, dpi=250, bbox_inches="tight")  # evita warning do tight_layout
    plt.close()
    log(f"Grafo salvo em: {outfile}", "ok", "green")

# ─────────────────────────────── main ───────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Gera grafo MuleSoft do ~/.m2")
    parser.add_argument("--out", metavar="IMG", type=Path,
                        help="Arquivo de saída (default: ./grafo_mulesoft.png)")
    parser.add_argument("--max", metavar="N", type=int, default=4,
                        help="Máx. de POMs MuleSoft a carregar (default: 4)")
    args = parser.parse_args()

    repo = Path.home() / ".m2" / "repository"
    if not repo.exists():
        log(f"Diretório {repo} não encontrado.", "err", "red")
        sys.exit(1)

    log(f"Varredura de: {repo}", "info")
    scan_m2(repo, max_mule_poms=args.max)
    log(f"Nós MuleSoft encontrados: {GRAPH.number_of_nodes()}", "info")

    outfile = args.out or (Path.cwd() / "grafo_mulesoft.png")
    draw_graph(GRAPH, outfile)

if __name__ == "__main__":
    main()
