from __future__ import annotations

import math
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4


WORD_PATTERN = re.compile(r"[a-zA-Z0-9_-]{3,}")
HEADING_PATTERN = re.compile(r"^#{1,6}\s+.+$", flags=re.MULTILINE)
STOPWORDS = {
    "and", "are", "but", "for", "from", "has", "have", "into", "that",
    "the", "this", "with", "you", "your", "una", "uno", "che", "con", "per",
    "gli", "del", "della", "delle", "sono", "come", "non",
}
NEGATION_TERMS = {"not", "never", "no", "without", "avoid", "cannot", "non", "mai", "senza"}
ASSERTION_TERMS = {"must", "should", "always", "use", "require", "requires", "deve", "sempre", "usa", "richiede"}


class KnowledgeWiki:
    """Markdown-backed shared memory with simple local relevance retrieval."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.proposals = self.root / "proposals"
        self.skills = self.root / "skills"
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.proposals.mkdir(parents=True, exist_ok=True)
        self.skills.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {
            term
            for term in (KnowledgeWiki._normalize_term(word) for word in WORD_PATTERN.findall(text))
            if term and term not in STOPWORDS
        }

    @staticmethod
    def _normalize_term(word: str) -> str:
        term = word.lower().strip("_-")
        for suffix in ("ing", "ed", "es", "s"):
            if len(term) > 5 and term.endswith(suffix):
                return term[: -len(suffix)]
        return term

    @classmethod
    def _term_counts(cls, text: str) -> Counter[str]:
        return Counter(
            term
            for term in (cls._normalize_term(word) for word in WORD_PATTERN.findall(text))
            if term and term not in STOPWORDS
        )

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str], idf: dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        numerator = sum(left[term] * right.get(term, 0) * idf.get(term, 1.0) for term in left)
        left_norm = math.sqrt(sum((count * idf.get(term, 1.0)) ** 2 for term, count in left.items()))
        right_norm = math.sqrt(sum((count * idf.get(term, 1.0)) ** 2 for term, count in right.items()))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)

    def pages(self) -> list[Path]:
        return sorted(
            path
            for path in self.root.rglob("*.md")
            if path.is_file()
            and self.proposals not in path.parents
            and not path.name.startswith("_")
        )

    @staticmethod
    def _strip_front_matter(content: str) -> str:
        text = str(content or "")
        if not text.startswith("---\n"):
            return text
        closing = text.find("\n---\n", 4)
        if closing < 0:
            return text
        return text[closing + 5 :]

    def _sections(self, path: Path, content: str) -> list[tuple[str, str]]:
        text = self._strip_front_matter(content).strip()
        if not text:
            return []
        matches = list(HEADING_PATTERN.finditer(text))
        if not matches:
            return [(str(path.relative_to(self.root)), text)]
        sections: list[tuple[str, str]] = []
        for index, match in enumerate(matches):
            heading = match.group(0).lstrip("#").strip()
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if not body:
                continue
            sections.append((f"{path.relative_to(self.root)} :: {heading}", body))
        return sections

    def _section_records(self) -> Iterator[dict[str, object]]:
        for path in self.pages():
            content = path.read_text(encoding="utf-8")
            sections = self._sections(path, content)
            if not sections:
                continue
            for name, section in sections:
                text = path.stem.replace("-", " ") + " " + name + " " + section
                yield {"path": path, "name": name, "content": section, "terms": self._term_counts(text)}

    def retrieve(self, query: str, limit: int = 4, max_characters: int = 10_000) -> list[tuple[str, str]]:
        query_counts = self._term_counts(query)
        records = list(self._section_records())
        if not query_counts or not records:
            return []
        document_frequency = Counter(
            term
            for record in records
            for term in set(record["terms"])
        )
        idf = {
            term: math.log((1 + len(records)) / (1 + frequency)) + 1.0
            for term, frequency in document_frequency.items()
        }
        query_text = " ".join(query.lower().split())
        ranked: list[tuple[float, str, str]] = []
        for record in records:
            content = str(record["content"])
            name = str(record["name"])
            score = self._cosine(query_counts, record["terms"], idf)
            heading_text = name.lower().replace("-", " ")
            if query_text and query_text in (heading_text + " " + content.lower()):
                score += 0.35
            score += 0.05 * len(set(query_counts) & set(record["terms"]))
            ranked.append((score, name, content))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected: list[tuple[str, str]] = []
        used = 0
        for score, name, content in ranked:
            if score <= 0:
                continue
            remaining = max_characters - used
            if remaining <= 0:
                break
            excerpt = content[:remaining]
            selected.append((name, excerpt))
            used += len(excerpt)
            if len(selected) >= limit:
                break
        return selected

    def search(self, query: str, limit: int = 4) -> dict[str, object]:
        matches = self.retrieve(query, limit=limit, max_characters=8_000)
        return {
            "query": query,
            "pages": [{"name": name, "content": content} for name, content in matches],
        }

    def list_pages(self) -> list[dict[str, object]]:
        pages: list[dict[str, object]] = []
        for path in self.pages():
            relative_name = path.relative_to(self.root).as_posix()
            content = path.read_text(encoding="utf-8")
            front_matter = self._front_matter(content)
            body = self._strip_front_matter(content)
            title = self._first_heading(content)
            kind = "journal" if path.name.startswith("agent-") and path.name.endswith("-journal.md") else "page"
            pages.append(
                {
                    "name": relative_name,
                    "title": title,
                    "updated": front_matter.get("updated") or front_matter.get("created") or "",
                    "kind": kind,
                    "sections": len(self._sections(path, content)),
                    "characters": len(body),
                }
            )
        return sorted(pages, key=lambda page: (str(page["kind"]) != "page", str(page["name"])))

    def get_page(self, name: str) -> dict[str, str]:
        requested = Path(name)
        safe_name = requested.as_posix().lstrip("/")
        if ".." in requested.parts or not safe_name:
            raise ValueError("Wiki page does not exist")
        if not safe_name.endswith(".md"):
            safe_name = f"{safe_name}.md"
        path = (self.root / safe_name).resolve()
        root = self.root.resolve()
        page_paths = {page.resolve() for page in self.pages()}
        if root not in path.parents or not path.is_file() or path not in page_paths:
            raise ValueError("Wiki page does not exist")
        return {"name": path.relative_to(root).as_posix(), "content": path.read_text(encoding="utf-8")}

    @staticmethod
    def _safe_page_name(page: str) -> str:
        text = str(page or "").lower().strip().replace("\\", "/").lstrip("/")
        if text.endswith(".md"):
            text = text[:-3]
        parts: list[str] = []
        for raw_part in text.split("/"):
            if raw_part in {"", ".", ".."}:
                if raw_part == "..":
                    return ""
                continue
            slug = re.sub(r"[^a-z0-9-]+", "-", raw_part).strip("-")
            if slug:
                parts.append(slug)
        return "/".join(parts)

    @staticmethod
    def _front_matter(content: str) -> dict[str, str]:
        text = str(content or "")
        if not text.startswith("---\n"):
            return {}
        closing = text.find("\n---\n", 4)
        if closing < 0:
            return {}
        front_matter: dict[str, str] = {}
        for line in text[4:closing].splitlines():
            key, separator, value = line.partition(":")
            if separator:
                front_matter[key.strip()] = value.strip()
        return front_matter

    @staticmethod
    def _first_heading(content: str) -> str:
        match = HEADING_PATTERN.search(KnowledgeWiki._strip_front_matter(content))
        if not match:
            return "Approved knowledge"
        return match.group(0).lstrip("#").strip()

    @staticmethod
    def _drop_first_heading(content: str) -> str:
        text = KnowledgeWiki._strip_front_matter(content).strip()
        match = HEADING_PATTERN.search(text)
        if not match or match.start() != 0:
            return text
        return text[match.end():].strip()

    @staticmethod
    def _drop_section(content: str, heading: str) -> str:
        text = str(content or "").strip()
        matches = list(HEADING_PATTERN.finditer(text))
        for index, match in enumerate(matches):
            current = match.group(0).lstrip("#").strip().lower()
            if current != heading.lower():
                continue
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return (text[: match.start()] + text[end:]).strip()
        return text

    def propose(
        self,
        agent_id: str,
        title: str,
        content: str,
        source: str,
        target_page: str = "shared-knowledge",
        confidence: float = 0.65,
    ) -> Path:
        with self._lock:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "update"
            safe_target = self._safe_page_name(target_page) or "shared-knowledge"
            conflicts = self.detect_conflicts(content, safe_target)
            conflict_lines = ""
            if conflicts:
                conflict_lines = "\nconflicts:\n" + "\n".join(
                    f"  - {item['page']} :: {item['section']} | overlap: {item['overlap']}"
                    for item in conflicts
                ) + "\n"
            conflict_body = ""
            if conflicts:
                conflict_body = "\n\n## Conflict warnings\n\n" + "\n".join(
                    f"- {item['page']} :: {item['section']} | overlap: {item['overlap']}"
                    for item in conflicts
                )
            path = self.proposals / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{slug}-{uuid4().hex[:6]}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"---\nstatus: proposed\nagent: {agent_id}\nsource: {source}\n"
                f"target_page: {safe_target}\n"
                f"confidence: {max(0.0, min(1.0, confidence)):.2f}\n"
                f"conflict: {str(bool(conflicts)).lower()}\n"
                f"{conflict_lines}"
                f"created: {datetime.now(timezone.utc).isoformat()}\n---\n\n# {title}\n\n{content.strip()}{conflict_body}\n",
                encoding="utf-8",
            )
            return path

    def detect_conflicts(self, content: str, target_page: str = "") -> list[dict[str, str]]:
        proposed_terms = self._terms(content)
        proposed_has_negation = bool(proposed_terms & NEGATION_TERMS)
        proposed_has_assertion = bool(proposed_terms & ASSERTION_TERMS)
        conflicts: list[dict[str, str]] = []
        paths = [self.root / f"{self._safe_page_name(target_page)}.md"] if target_page else self.pages()
        for path in paths:
            if not path.is_file():
                continue
            for name, section in self._sections(path, path.read_text(encoding="utf-8")):
                section_terms = self._terms(section)
                overlap = proposed_terms & section_terms
                if len(overlap) < 4:
                    continue
                section_has_negation = bool(section_terms & NEGATION_TERMS)
                section_has_assertion = bool(section_terms & ASSERTION_TERMS)
                if proposed_has_negation != section_has_negation and (proposed_has_assertion or section_has_assertion):
                    conflicts.append(
                        {
                            "page": path.name,
                            "section": name,
                            "overlap": ", ".join(sorted(overlap)[:12]),
                        }
                    )
        return conflicts[:5]

    def pending_proposals(self, limit: int = 20) -> list[dict[str, str]]:
        return [
            {"name": path.name, "content": path.read_text(encoding="utf-8")}
            for path in sorted(self.proposals.glob("*.md"))[:limit]
        ]

    def resolve_proposal(
        self, name: str, status: str, reviewer: str, reason: str
    ) -> Path:
        with self._lock:
            if status not in {"approved", "rejected"}:
                raise ValueError("Proposal status must be approved or rejected")
            source = self.proposals / Path(name).name
            if source.parent != self.proposals or not source.is_file() or source.suffix != ".md":
                raise ValueError("Wiki proposal does not exist")
            reviewed = self.proposals / "reviewed"
            reviewed.mkdir(parents=True, exist_ok=True)
            destination = reviewed / f"{status}-{source.name}"
            content = source.read_text(encoding="utf-8")
            front_matter = self._front_matter(content)
            if status == "approved" and front_matter.get("conflict", "").lower() == "true":
                reason_text = reason.lower()
                if "override conflict" not in reason_text and "override-conflict" not in reason_text:
                    raise ValueError("Conflicting wiki proposals require review reason to include 'override conflict'")
            if status == "approved":
                self._promote_approved_proposal(content)
            destination.write_text(
                content
                + f"\n## Review\n\n- Status: {status}\n- Reviewer: {reviewer}\n"
                + f"- Reviewed: {datetime.now(timezone.utc).isoformat()}\n- Reason: {reason.strip()}\n",
                encoding="utf-8",
            )
            source.unlink()
            return destination

    def _promote_approved_proposal(self, content: str) -> Path:
        front_matter = self._front_matter(content)
        target_page = front_matter.get("target_page") or "shared-knowledge"
        agent_id = front_matter.get("agent") or "unknown"
        source = front_matter.get("source") or "wiki-proposal"
        heading = self._first_heading(content)
        body = self._drop_section(self._drop_first_heading(content), "Conflict warnings")
        return self.append_journal_entry(
            page=target_page,
            heading=heading,
            content=body,
            agent_id=agent_id,
            source=source,
            max_characters=64_000,
        )

    def update_page(self, page: str, content: str, agent_id: str, source: str) -> Path:
        with self._lock:
            safe_name = self._safe_page_name(page)
            if not safe_name:
                raise ValueError("Wiki page name is invalid")
            path = self.root / f"{safe_name}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"---\nupdated_by: {agent_id}\nsource: {source}\n"
                f"updated: {datetime.now(timezone.utc).isoformat()}\n---\n\n{content.strip()}\n",
                encoding="utf-8",
            )
            return path

    def append_journal_entry(
        self,
        page: str,
        heading: str,
        content: str,
        agent_id: str,
        source: str,
        max_characters: int = 32_000,
    ) -> Path:
        with self._lock:
            safe_name = self._safe_page_name(page)
            if not safe_name:
                raise ValueError("Wiki page name is invalid")
            path = self.root / f"{safe_name}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            body = self._strip_front_matter(existing).strip()
            entry = (
                f"## {heading.strip()}\n\n"
                f"{content.strip()}\n\n"
                f"- agent: {agent_id}\n"
                f"- source: {source}\n"
                f"- updated: {datetime.now(timezone.utc).isoformat()}\n"
            ).strip()
            merged = f"{body}\n\n{entry}".strip() if body else entry
            merged = self._trim_sections(merged, max_characters)
            path.write_text(
                f"---\nupdated_by: {agent_id}\nsource: {source}\n"
                f"updated: {datetime.now(timezone.utc).isoformat()}\n---\n\n{merged}\n",
                encoding="utf-8",
            )
            return path

    def consolidate_page(self, page: str) -> dict[str, object]:
        with self._lock:
            requested = Path(page)
            safe_name = requested.as_posix().lstrip("/")
            if ".." in requested.parts or not safe_name:
                raise ValueError("Wiki page does not exist")
            if not safe_name.endswith(".md"):
                safe_name = f"{safe_name}.md"
            path = (self.root / safe_name).resolve()
            root = self.root.resolve()
            page_paths = {page.resolve() for page in self.pages()}
            if root not in path.parents or not path.is_file() or path not in page_paths:
                raise ValueError("Wiki page does not exist")
            content = path.read_text(encoding="utf-8")
            front_matter = self._front_matter(content)
            sections = self._sections(path, content)
            seen: set[str] = set()
            deduped: list[str] = []
            removed = 0
            for name, section in sections:
                normalized = " ".join(sorted(self._terms(section)))
                if normalized and normalized in seen:
                    removed += 1
                    continue
                seen.add(normalized)
                deduped.append(section.strip())
            if removed == 0:
                return {"page": path.relative_to(root).as_posix(), "updated": False, "duplicate_sections_removed": 0}
            updated = datetime.now(timezone.utc).isoformat()
            source = front_matter.get("source") or "wiki-maintenance"
            agent_id = front_matter.get("updated_by") or "runtime"
            path.write_text(
                f"---\nupdated_by: {agent_id}\nsource: {source}\nupdated: {updated}\nconsolidated: {updated}\n---\n\n"
                + "\n\n".join(deduped).strip()
                + "\n",
                encoding="utf-8",
            )
            return {"page": path.relative_to(root).as_posix(), "updated": True, "duplicate_sections_removed": removed}

    def _trim_sections(self, body: str, max_characters: int) -> str:
        text = body.strip()
        if len(text) <= max_characters:
            return text
        matches = list(HEADING_PATTERN.finditer(text))
        if not matches:
            return text[-max_characters:].lstrip()
        chunks: list[str] = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            chunks.append(text[match.start():end].strip())
        kept: list[str] = []
        used = 0
        for chunk in reversed(chunks):
            addition = len(chunk) + (2 if kept else 0)
            if kept and used + addition > max_characters:
                break
            if not kept and len(chunk) > max_characters:
                kept.append(chunk[-max_characters:].lstrip())
                break
            kept.append(chunk)
            used += addition
        return "\n\n".join(reversed(kept)).strip()

    def maintain(self) -> dict[str, object]:
        with self._lock:
            pages = self.pages()
            pages_updated = 0
            duplicates_removed = 0
            for path in pages:
                result = self.consolidate_page(path.relative_to(self.root).as_posix())
                if result["updated"]:
                    pages_updated += 1
                    duplicates_removed += int(result["duplicate_sections_removed"])
            index_lines = ["# Wiki index", ""]
            for page in self.list_pages():
                index_lines.append(
                    f"- {page['name']}: {page['title']} ({page['sections']} sections, {page['characters']} chars)"
                )
            index_path = self.update_page(
                "index",
                "\n".join(index_lines),
                agent_id="runtime",
                source="wiki-maintenance",
            )
            return {
                "pages_scanned": len(pages),
                "pages_updated": pages_updated,
                "duplicate_sections_removed": duplicates_removed,
                "index_page": index_path.name,
            }

    def record_workflow_skill(
        self,
        workflow_id: str,
        objective: str,
        steps: list[dict[str, str]],
        outcome: str,
        orchestrator_id: str,
    ) -> Path:
        with self._lock:
            slug = re.sub(r"[^a-z0-9]+", "-", objective.lower()).strip("-")[:60] or "workflow"
            path = self.skills / f"{slug}.md"
            previous = path.read_text(encoding="utf-8") if path.exists() else ""
            uses_match = re.search(r"^uses:\s*(\d+)$", previous, flags=re.MULTILINE)
            uses = int(uses_match.group(1)) + 1 if uses_match else 1
            history = re.findall(r"^- .+$", previous, flags=re.MULTILINE)[-4:]
            history.append(f"- {datetime.now(timezone.utc).date()}: {outcome[:500]}")
            history_text = "\n".join(history)
            procedure = "\n".join(
                f"{index}. **{step['title']}** ({step.get('agent', 'unassigned')}): "
                f"{step.get('result', 'No result recorded')}"
                for index, step in enumerate(steps, start=1)
            )
            path.write_text(
                f"---\ntype: learned-skill\nworkflow: {workflow_id}\n"
                f"created_by: {orchestrator_id}\ncreated: {datetime.now(timezone.utc).isoformat()}\n"
                f"uses: {uses}\nstatus: active\n---\n\n"
                f"# Learned workflow: {objective[:120]}\n\n"
                f"## When to use\n\nUse this procedure for objectives similar to: {objective}\n\n"
                f"## Procedure\n\n{procedure}\n\n"
                f"## Verified outcome\n\n{outcome}\n\n"
                f"## Refinement history\n\n{history_text}\n",
                encoding="utf-8",
            )
            return path
