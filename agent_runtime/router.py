from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from .models import AgentSnapshot, TaskRecord


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_phrase(text: str, phrases: set[str]) -> bool:
    padded = f" {text} "
    return any(f" {phrase} " in padded for phrase in phrases if phrase)


ROUTE_VERBS = {
    "talk", "speak", "ask", "tell", "contact", "message", "send", "pass", "route", "transfer", "connect",
    "parla", "parlare", "parli", "chiedi", "chiedere", "dire", "dici", "contatta", "manda", "passa",
    "habla", "hablar", "pregunta", "preguntar", "dile", "decir", "contacta", "envia", "manda",
    "parlez", "parler", "demande", "demander", "dis", "dire", "contacte", "envoye", "envoyer",
    "sprich", "sprechen", "frage", "fragen", "sage", "sagen", "kontaktiere", "sende",
    "fale", "falar", "pergunte", "perguntar", "diga", "dizer", "contate", "envie",
}

DIRECT_ROUTE_PHRASES = {
    "talk to", "talk with", "speak to", "speak with", "ask the", "ask", "tell", "route to", "send to", "pass to",
    "parla con", "parlare con", "vai a parlare con", "chiedi a", "di a", "manda a", "passa a",
    "habla con", "pregunta a", "dile a", "envia a", "manda a",
    "parle a", "parle avec", "demande a", "dis a", "envoie a",
    "sprich mit", "frage", "sag", "sende an",
    "fale com", "pergunte a", "diga a", "envie para",
}

USER_ROUTE_HINTS = {
    "let me talk to", "i want to talk to", "connect me to", "switch to", "open the chat with",
    "fammi parlare con", "voglio parlare con", "passami", "connettimi a", "apri la chat con",
    "quiero hablar con", "conectame con", "abre el chat con",
    "je veux parler a", "connecte moi a", "ouvre le chat avec",
}

AGENT_CONSULT_HINTS = {
    "ask the", "tell the", "go talk to", "please talk to", "you should talk to",
    "chiedi a", "di a", "vai a parlare con", "devi parlare con", "parla con",
    "pregunta a", "dile a", "habla con",
    "demande a", "dis a", "parle avec",
}

LANGUAGE_HINTS = {
    "it": {"ciao", "parla", "ricerca", "agente", "devi", "voglio", "con"},
    "en": {"hello", "talk", "agent", "research", "with", "please"},
    "es": {"hola", "habla", "agente", "investiga", "con", "por"},
    "fr": {"bonjour", "parle", "agent", "recherche", "avec", "pour"},
    "de": {"hallo", "sprich", "agent", "forschung", "mit", "bitte"},
    "pt": {"ola", "fale", "agente", "pesquisa", "com", "por"},
}

AGENT_ALIASES = {
    "orchestrator": {"orchestrator", "coord", "coordinator", "orchestratore", "coordinatore"},
    "researcher": {"researcher", "research", "ricercatore", "ricerca", "chercheur", "investigador", "investigator"},
    "planner": {"planner", "planning", "pianificatore", "pianificazione", "planificador", "planificateur"},
    "builder": {"builder", "implementer", "dev", "developer", "costruttore", "sviluppatore", "implementatore"},
    "critic": {"critic", "reviewer", "critico", "revisore", "review", "qa"},
    "scheduler": {"scheduler", "schedule", "calendar", "cron", "schedulatore", "calendario"},
    "memory": {"memory", "memory core", "memoria", "wiki", "knowledge", "context"},
}

CAPABILITY_KEYWORDS = {
    "research": {
        "research", "search", "find", "look up", "source", "sources", "evidence", "news", "trend", "trends",
        "ricerca", "cerca", "cercare", "fonti", "fonte", "notizie", "trend", "evidenza",
        "buscar", "investiga", "investigar", "fuentes", "noticias",
        "recherche", "chercher", "sources", "actualites",
    },
    "planning": {
        "plan", "planning", "organize", "organise", "strategy", "steps", "roadmap", "decompose",
        "piano", "pianifica", "pianificare", "strategia", "passi", "roadmap", "organizza",
        "planifica", "pasos", "estrategia",
        "planifier", "strategie", "etapes", "organiser",
    },
    "scheduling": {
        "schedule", "calendar", "tomorrow", "today", "next week", "cron", "repeat", "daily", "weekly", "time",
        "programma", "calendario", "domani", "oggi", "settimana", "cron", "ripeti", "giornaliero", "orario",
        "agenda", "manana", "hoy", "semana", "repetir", "hora",
        "calendrier", "demain", "aujourd hui", "semaine", "horaire",
    },
    "implementation": {
        "build", "implement", "code", "fix", "patch", "integrate", "edit", "change", "feature", "bug",
        "costruisci", "implementa", "codice", "fixa", "correggi", "patch", "integra", "modifica", "feature", "bug",
        "construye", "implementa", "codigo", "corrige", "integra",
        "construire", "implementer", "code", "corriger", "integrer",
    },
    "review": {
        "review", "check", "verify", "validate", "test", "risk", "bug", "regression", "security",
        "rivedi", "controlla", "verifica", "valida", "test", "rischio", "regressione", "sicurezza",
        "revisa", "verifica", "riesgo", "seguridad",
        "revise", "verifie", "risque", "securite",
    },
    "memory": {
        "remember", "memory", "context", "wiki", "knowledge", "recall", "store", "save this",
        "ricorda", "memoria", "contesto", "wiki", "conoscenza", "richiama", "salva questo",
        "recuerda", "memoria", "contexto", "guardar",
        "memoire", "contexte", "rappelle", "sauvegarde",
    },
    "news": {
        "news", "latest", "recent", "headlines", "briefing", "morning summary", "ai news",
        "notizie", "ultime", "recenti", "briefing", "riepilogo mattutino",
        "noticias", "ultimas", "resumen",
        "actualites", "dernieres", "resume",
    },
}


@dataclass(frozen=True)
class ChatRouteDecision:
    should_route: bool
    target_agent_id: str = ""
    route_mode: str = "route"
    reason: str = ""
    language: str = ""
    forwarded_message: str = ""
    clarification_question: str = ""
    confidence: float = 0.0


class ConversationRouter:
    @staticmethod
    def normalize_text(text: str) -> str:
        return _normalize(text)

    def detect_language(self, text: str) -> str:
        normalized = _normalize(text)
        if not normalized:
            return ""
        tokens = set(normalized.split())
        best_language = ""
        best_score = 0
        for language, hints in LANGUAGE_HINTS.items():
            score = len(tokens & hints)
            if score > best_score:
                best_score = score
                best_language = language
        return best_language

    def route_chat(
        self,
        task: TaskRecord,
        agents: dict[str, AgentSnapshot],
    ) -> ChatRouteDecision:
        if task.channel != "chat" or not task.requested_agent_id or task.requested_agent_id not in agents:
            return ChatRouteDecision(False)
        text = (task.description or task.title or "").strip()
        normalized = _normalize(text)
        if not normalized:
            return ChatRouteDecision(False)
        current_agent = agents.get(task.requested_agent_id)
        current_id = current_agent.id if current_agent else ""
        best_target: Optional[AgentSnapshot] = None
        best_score = 0
        route_signal = 0
        ranked_targets: list[tuple[int, AgentSnapshot]] = []
        explicitly_mentioned_agents: list[AgentSnapshot] = []

        tokens = set(normalized.split())
        if tokens & ROUTE_VERBS:
            route_signal += 2
        if _contains_phrase(normalized, DIRECT_ROUTE_PHRASES):
            route_signal += 3

        for agent in agents.values():
            score = 0
            aliases = self._aliases_for(agent)
            capability_aliases = {_normalize(capability) for capability in agent.capabilities}
            for alias in aliases:
                alias_normalized = _normalize(alias)
                if not alias_normalized:
                    continue
                padded = f" {normalized} "
                if f" {alias_normalized} " not in padded:
                    continue
                if alias_normalized == agent.id:
                    score = max(score, 12)
                elif alias_normalized == _normalize(agent.name):
                    score = max(score, 11)
                elif alias_normalized == _normalize(agent.role):
                    score = max(score, 8)
                elif alias_normalized in capability_aliases:
                    score = max(score, 7)
                else:
                    score = max(score, 9)
            if score >= 9:
                explicitly_mentioned_agents.append(agent)
            score += self._capability_score(normalized, agent)
            if score > 0:
                ranked_targets.append((score, agent))
            if score > best_score:
                best_target = agent
                best_score = score

        ranked_targets.sort(key=lambda item: (-item[0], item[1].name))
        clarification = self._clarification_decision(
            normalized,
            route_signal,
            ranked_targets,
            current_agent,
            explicitly_mentioned_agents,
        )
        if clarification is not None:
            return clarification

        if not best_target or best_target.id == current_id:
            return ChatRouteDecision(False)
        current_score = self._capability_score(normalized, current_agent) if current_agent else 0
        explicit_route = route_signal > 0 and best_score >= 7
        implicit_route = (
            best_score >= 4
            and best_score >= current_score + 3
            and self._should_implicitly_route(current_agent, best_target, text, normalized)
        )
        if not explicit_route and not implicit_route:
            return ChatRouteDecision(False)

        language = self.detect_language(text)
        route_mode = self._route_mode(normalized, current_agent, explicit_route)
        forwarded = self._forwarded_message(text, current_agent, best_target, language, route_mode)
        confidence = min(
            0.99,
            0.45 + best_score * 0.035 + route_signal * 0.06 + (0.08 if implicit_route else 0),
        )
        return ChatRouteDecision(
            should_route=True,
            target_agent_id=best_target.id,
            route_mode=route_mode,
            reason=(
                f"Detected {route_mode} request from {current_id} to {best_target.id}."
                if explicit_route
                else f"Inferred that {best_target.id} should be consulted because it is better suited than {current_id or 'current agent'}."
            ),
            language=language,
            forwarded_message=forwarded,
            confidence=confidence,
        )

    def _clarification_decision(
        self,
        normalized_text: str,
        route_signal: int,
        ranked_targets: list[tuple[int, AgentSnapshot]],
        current_agent: Optional[AgentSnapshot],
        explicitly_mentioned_agents: list[AgentSnapshot],
    ) -> Optional[ChatRouteDecision]:
        explicit_unique = list(dict.fromkeys(agent.id for agent in explicitly_mentioned_agents))
        if route_signal > 0 and len(explicit_unique) >= 2:
            unique_agents: list[AgentSnapshot] = []
            seen_ids: set[str] = set()
            for agent in explicitly_mentioned_agents:
                if agent.id in seen_ids:
                    continue
                seen_ids.add(agent.id)
                unique_agents.append(agent)
            unique_agents.sort(key=lambda agent: agent.name)
            first = unique_agents[0]
            second = unique_agents[1]
            current_label = current_agent.name if current_agent else "the current agent"
            return ChatRouteDecision(
                should_route=False,
                target_agent_id=current_agent.id if current_agent else "",
                route_mode="clarify",
                reason=f"Routing is ambiguous between {first.id} and {second.id}.",
                clarification_question=(
                    f"Do you want me to keep this with {current_label}, "
                    f"or should I move it to {first.name} or {second.name}?"
                ),
                confidence=0.28,
            )
        if route_signal <= 0 or len(ranked_targets) < 2:
            return None
        top_score, top_agent = ranked_targets[0]
        second_score, second_agent = ranked_targets[1]
        if top_agent.id == second_agent.id:
            return None
        if top_score - second_score > 1:
            return None
        labels = f"{top_agent.name} or {second_agent.name}"
        current_label = current_agent.name if current_agent else "the current agent"
        return ChatRouteDecision(
            should_route=False,
            target_agent_id=current_agent.id if current_agent else "",
            route_mode="clarify",
            reason=f"Routing is ambiguous between {top_agent.id} and {second_agent.id}.",
            clarification_question=(
                f"Do you want me to keep this with {current_label}, "
                f"or should I move it to {labels}?"
            ),
            confidence=0.34,
        )

    def _capability_score(self, normalized_text: str, agent: Optional[AgentSnapshot]) -> int:
        if agent is None:
            return 0
        score = 0
        padded = f" {normalized_text} "
        for capability in agent.capabilities or []:
            capability_normalized = _normalize(capability)
            if capability_normalized and f" {capability_normalized} " in padded:
                score += 3
            for keyword in CAPABILITY_KEYWORDS.get(capability_normalized, set()):
                keyword_normalized = _normalize(keyword)
                if keyword_normalized and f" {keyword_normalized} " in padded:
                    score += 2
        role_normalized = _normalize(agent.role)
        if role_normalized and f" {role_normalized} " in padded:
            score += 2
        return score

    @staticmethod
    def _should_implicitly_route(
        current_agent: Optional[AgentSnapshot],
        target_agent: AgentSnapshot,
        raw_text: str,
        normalized_text: str,
    ) -> bool:
        if current_agent is None:
            return True
        if current_agent.id in {"orchestrator", "memory"}:
            return True
        if "?" in str(raw_text or ""):
            return False
        current_caps = {_normalize(capability) for capability in current_agent.capabilities or []}
        target_caps = {_normalize(capability) for capability in target_agent.capabilities or []}
        return not target_caps.issubset(current_caps)

    @staticmethod
    def _route_mode(
        normalized_text: str,
        current_agent: Optional[AgentSnapshot],
        explicit_route: bool,
    ) -> str:
        if not explicit_route:
            return "consult"
        if _contains_phrase(normalized_text, USER_ROUTE_HINTS):
            return "route"
        if _contains_phrase(normalized_text, AGENT_CONSULT_HINTS):
            return "consult"
        if current_agent and current_agent.id in {"orchestrator", "memory"}:
            return "consult"
        return "route"

    def _aliases_for(self, agent: AgentSnapshot) -> set[str]:
        aliases = {
            agent.id,
            agent.name,
            agent.role,
            *(agent.capabilities or []),
        }
        aliases.update(AGENT_ALIASES.get(agent.id, set()))
        return {alias for alias in aliases if str(alias or "").strip()}

    @staticmethod
    def _forwarded_message(
        original_text: str,
        source_agent: Optional[AgentSnapshot],
        target_agent: AgentSnapshot,
        language: str,
        route_mode: str,
    ) -> str:
        source_name = source_agent.name if source_agent else "another agent"
        language_line = f"Detected user language: {language}." if language else ""
        reply_line = (
            f"Reply in the same language as the user ({language})."
            if language
            else "Reply in the same language as the user whenever it is clear from the message."
        )
        mode_line = (
            f"You are being consulted by {source_name}; provide the best specialist answer for them to relay to the user."
            if route_mode == "consult"
            else f"The user asked to continue this conversation with {target_agent.name}."
        )
        return "\n".join(
            line
            for line in (
                mode_line,
                f"The request was originally received by {source_name}.",
                language_line,
                reply_line,
                "Continue directly with the user's intent instead of explaining routing limitations.",
                "",
                f"Original user message:\n{original_text.strip()}",
            )
            if line
        ).strip()
