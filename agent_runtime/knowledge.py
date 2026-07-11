from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


WORD_PATTERN = re.compile(r"[a-zA-Z0-9_-]{3,}")


class KnowledgeWiki:
    """Markdown-backed shared memory with simple local relevance retrieval."""

    def __init__(self, root: Path):
        self.root = root
        self.proposals = root / "proposals"
        self.skills = root / "skills"
        self.root.mkdir(parents=True, exist_ok=True)
        self.proposals.mkdir(parents=True, exist_ok=True)
        self.skills.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {word.lower() for word in WORD_PATTERN.findall(text)}

    def pages(self) -> list[Path]:
        return sorted(
            path
            for path in self.root.rglob("*.md")
            if path.is_file()
            and self.proposals not in path.parents
            and not path.name.startswith("_")
        )

    def retrieve(self, query: str, limit: int = 4, max_characters: int = 10_000) -> list[tuple[str, str]]:
        query_terms = self._terms(query)
        ranked: list[tuple[int, str, str]] = []
        for path in self.pages():
            content = path.read_text(encoding="utf-8")
            score = len(query_terms & self._terms(path.stem.replace("-", " ") + " " + content))
            ranked.append((score, str(path.relative_to(self.root)), content))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected: list[tuple[str, str]] = []
        used = 0
        for score, name, content in ranked:
            if selected and score == 0:
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

    def propose(self, agent_id: str, title: str, content: str, source: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "update"
        path = self.proposals / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{slug}-{uuid4().hex[:6]}.md"
        path.write_text(
            f"---\nstatus: proposed\nagent: {agent_id}\nsource: {source}\n"
            f"created: {datetime.now(timezone.utc).isoformat()}\n---\n\n# {title}\n\n{content.strip()}\n",
            encoding="utf-8",
        )
        return path

    def pending_proposals(self, limit: int = 20) -> list[dict[str, str]]:
        return [
            {"name": path.name, "content": path.read_text(encoding="utf-8")}
            for path in sorted(self.proposals.glob("*.md"))[:limit]
        ]

    def resolve_proposal(
        self, name: str, status: str, reviewer: str, reason: str
    ) -> Path:
        if status not in {"approved", "rejected"}:
            raise ValueError("Proposal status must be approved or rejected")
        source = self.proposals / Path(name).name
        if source.parent != self.proposals or not source.is_file() or source.suffix != ".md":
            raise ValueError("Wiki proposal does not exist")
        reviewed = self.proposals / "reviewed"
        reviewed.mkdir(parents=True, exist_ok=True)
        destination = reviewed / f"{status}-{source.name}"
        content = source.read_text(encoding="utf-8")
        destination.write_text(
            content
            + f"\n## Review\n\n- Status: {status}\n- Reviewer: {reviewer}\n"
            + f"- Reviewed: {datetime.now(timezone.utc).isoformat()}\n- Reason: {reason.strip()}\n",
            encoding="utf-8",
        )
        source.unlink()
        return destination

    def update_page(self, page: str, content: str, agent_id: str, source: str) -> Path:
        safe_name = re.sub(r"[^a-z0-9-]+", "-", page.lower()).strip("-")
        if not safe_name:
            raise ValueError("Wiki page name is invalid")
        path = self.root / f"{safe_name}.md"
        path.write_text(
            f"---\nupdated_by: {agent_id}\nsource: {source}\n"
            f"updated: {datetime.now(timezone.utc).isoformat()}\n---\n\n{content.strip()}\n",
            encoding="utf-8",
        )
        return path

    def record_workflow_skill(
        self,
        workflow_id: str,
        objective: str,
        steps: list[dict[str, str]],
        outcome: str,
        orchestrator_id: str,
    ) -> Path:
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
