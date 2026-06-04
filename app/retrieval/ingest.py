from pathlib import Path
import os
from llama_index.core import SimpleDirectoryReader, Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
import re
from app.retrieval.embeddings import get_embed_model
from typing import List
from app.retrieval.index import build_index, TABLE_NAME, EMBED_DIM

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT_DIR / "knowledge" / "raw"


def _guess_doc_type(filename: str) -> str:
    """根据文件名推断 doc_type（与 week-02 metadata 规范一致）。"""
    upper = filename.upper()
    if "FAQ" in upper:
        return "faq"
    if "POLICY" in upper:
        return "policy"
    return "regulation"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _extract_sections(full_text: str) -> list[tuple[int, str]]:
    """全文里所有 Markdown 标题及起始位置。"""
    return [(m.start(), m.group(2).strip()) for m in _HEADING_RE.finditer(full_text)]


def _section_for_offset(sections: list[tuple[int, str]], offset: int) -> str:
    """chunk 起始位置对应的最近标题。"""
    title = ""
    for pos, name in sections:
        if pos <= offset:
            title = name
        else:
            break
    return title or "未分类"


def enrich_section_metadata(nodes: list[TextNode], docs: list[Document]) -> None:
    """给每个 node 写入 section（最近的上级/当前标题）。"""
    doc_by_path = {d.metadata.get("file_path", ""): d for d in docs}

    for node in nodes:
        fp = node.metadata.get("file_path", "")
        doc = doc_by_path.get(fp)
        if not doc:
            node.metadata.setdefault("section", "未分类")
            continue

        full_text = doc.get_content(metadata_mode="none")
        sections = _extract_sections(full_text)
        offset = node.start_char_idx
        if offset is not None:
            node.metadata["section"] = _section_for_offset(sections, offset)
        else:
            node.metadata["section"] = "未分类"

def load_documents(file_path: Path) -> List[Document]:
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    reader = SimpleDirectoryReader(
        input_dir=str(file_path),
        recursive=True,
        required_exts=[".md"],  # 按需
    )

    docs = reader.load_data()
    for doc in docs:
        path = Path(doc.metadata.get("file_path", ""))
        doc.metadata.setdefault("source", path.name)
        doc.metadata.setdefault("doc_type", _guess_doc_type(path.name))
        # section 可在分块后从标题再 enrich，或先留空
    return docs

def chunk_documents(docs: List[Document], chunk_size: int = 512, chunk_overlap: int = 64) -> List[TextNode]:
    text_splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return text_splitter.get_nodes_from_documents(docs)


def run_ingest(raw_dir: Path | None = None) -> list[TextNode]:
    raw_dir = raw_dir or RAW_DIR
    docs = load_documents(raw_dir)
    nodes = chunk_documents(docs)
    enrich_section_metadata(nodes, docs)
    print("section:", nodes[0].metadata.get("section"))
    return nodes

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--rebuild", action="store_true")  # Day 3 给 index 用
    args = parser.parse_args()

    nodes = run_ingest(args.raw_dir)
    print(f"documents → nodes: {len(nodes)}")

    from app.retrieval.index import build_index
    index = build_index(nodes, rebuild=args.rebuild)
    print(f"index built → table={TABLE_NAME}, dim={EMBED_DIM}")

    for i, node in enumerate(nodes[:1]):  # 只看前 5 片
        print(f"\n--- chunk {i} ---")
        print("source:", node.metadata.get("source"))
        print("doc_type:", node.metadata.get("doc_type"))
        print("text_len:", len(node.text))
        print("text_preview:\n", node.text[:400], "...\n")
        # 入库后 node 上可能有 embedding；没有则再算一次（仅调试用）
        emb = getattr(node, "embedding", None)
        if emb is None:

            emb = get_embed_model().get_text_embedding(
                node.get_content(metadata_mode="none")  # 或 node.text
            )
        print("vector_dim:", len(emb))
        print("vector_head:", emb[:8])  

if __name__ == "__main__":
    main()