"""Phase 9D — versioned local domain knowledge packs + canonical-form quality.

Two 9D objectives:

1. CANONICAL-FORM QUALITY (mandatory). 9F showed exact-entity accuracy was
   capped because package canonicals were lowercase (fastapi, sqlalchemy,
   tensorflow) while references need FastAPI / SQLAlchemy / TensorFlow. This is
   fixed with an EVIDENCE-DRIVEN canonical map (the official published casing of
   each project), NOT generic title-casing. Each term carries a
   ``canonical_confidence`` so the ranker can prefer high-confidence canonicals.

2. VERSIONED DOMAIN PACKS. Small, curated, independent, disableable packs per
   domain (AI/ML, security, devops, web, databases, data engineering,
   academic). Each pack is a list of DomainTerm records with source +
   confidence + ambiguity class.

Everything is local, inert data; no network, no runtime dataset download.
Packs convert to the existing ``KnowledgeTerm`` so the 9C index + 9F ranker +
9B corrector are reused unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..knowledge.models import Domain, KnowledgeTerm

PACK_SCHEMA_VERSION = "9d.1"
CANONICAL_VERSION = "9d.1"

# Confidence tiers (explicit, not invented per-entry): official project identity
# is the most trustworthy canonical source.
CONF_OFFICIAL = 0.95     # official/project-published canonical casing
CONF_CURATED = 0.9       # hand-reviewed
CONF_STRUCTURED = 0.7    # structured metadata (e.g. Linguist)
CONF_GENERIC = 0.4       # generic fallback

# Ambiguity classes.
AMB_NONE = "none"            # unambiguous technical entity
AMB_ORDINARY = "ordinary"    # collides with an ordinary English word
AMB_PROPER = "proper"        # collides with a proper name/company


@dataclass
class DomainTerm:
    spoken_form: str                 # representative spoken/normalized form
    canonical_form: str              # official written form to emit
    aliases: Tuple[str, ...] = ()    # additional spoken variants
    domain: str = Domain.DEVELOPER
    category: str = "term"
    source: str = "curated"
    source_confidence: float = CONF_CURATED
    canonical_confidence: float = CONF_CURATED
    ambiguity_class: str = AMB_NONE
    enabled: bool = True
    version: str = PACK_SCHEMA_VERSION

    def to_knowledge_term(self) -> KnowledgeTerm:
        # spoken_variants = spoken_form + aliases (lowercase surface forms);
        # canonical_form is the emitted form. relevance blends the two
        # confidences so the ranker favors high-quality canonical entities.
        variants = tuple(dict.fromkeys([self.spoken_form, *self.aliases]))
        return KnowledgeTerm(
            canonical=self.canonical_form,
            spoken_variants=variants,
            category=self.category,
            domain=self.domain,
            source=self.source,
            relevance=round(0.5 * self.source_confidence + 0.5 * self.canonical_confidence, 3),
            metadata={"canonical_confidence": str(self.canonical_confidence),
                      "ambiguity_class": self.ambiguity_class,
                      "pack_version": self.version},
        )


def _t(spoken, canonical, domain, category, aliases=(), amb=AMB_NONE,
       source="curated", sconf=CONF_CURATED, cconf=CONF_OFFICIAL) -> DomainTerm:
    return DomainTerm(spoken_form=spoken, canonical_form=canonical, aliases=aliases,
                      domain=domain, category=category, source=source,
                      source_confidence=sconf, canonical_confidence=cconf,
                      ambiguity_class=amb)


# ---------------------------------------------------------------------------
# Domain packs. Canonical forms are the official published casings (evidence-
# driven), with the real spoken mis-hearings as aliases where known.
# ---------------------------------------------------------------------------

_AI_ML = [
    _t("tensorflow", "TensorFlow", Domain.AI_ML, "library", ("tensor flow",)),
    _t("pytorch", "PyTorch", Domain.AI_ML, "library", ("pie torch", "py torch")),
    _t("scikit learn", "scikit-learn", Domain.AI_ML, "library", ("sklearn", "scikit-learn")),
    _t("numpy", "NumPy", Domain.AI_ML, "library", ("num pie", "num py")),
    _t("pandas", "pandas", Domain.AI_ML, "library", (), AMB_ORDINARY),
    _t("onnx", "ONNX", Domain.AI_ML, "format", ("o n n x",)),
    _t("hugging face", "Hugging Face", Domain.AI_ML, "platform", ("huggingface",)),
    _t("transformers", "Transformers", Domain.AI_ML, "library", (), AMB_ORDINARY),
    _t("langchain", "LangChain", Domain.AI_ML, "library", ("lang chain",)),
    _t("vector database", "vector database", Domain.AI_ML, "phrase"),
    _t("machine learning", "machine learning", Domain.AI_ML, "phrase"),
    _t("embeddings", "embeddings", Domain.AI_ML, "term", (), AMB_ORDINARY),
]

_SECURITY = [
    _t("web auth n", "WebAuthn", Domain.SECURITY, "protocol", ("webauthn", "web auth", "webant")),
    _t("o auth two", "OAuth2", Domain.SECURITY, "protocol", ("oauth2", "oauth 2", "o auth")),
    _t("open id connect", "OpenID Connect", Domain.SECURITY, "protocol", ("openid connect",)),
    _t("jot", "JWT", Domain.SECURITY, "standard", ("jwt", "j w t")),
    _t("tls", "TLS", Domain.SECURITY, "protocol", ("t l s",)),
    _t("mtls", "mTLS", Domain.SECURITY, "protocol", ("m t l s", "mutual tls")),
    _t("saml", "SAML", Domain.SECURITY, "standard", ("sam el",)),
    _t("rbac", "RBAC", Domain.SECURITY, "term", ("r b a c",)),
    _t("fido two", "FIDO2", Domain.SECURITY, "standard", ("fido2", "fido 2")),
]

_DEVOPS = [
    _t("kubernetes", "Kubernetes", Domain.DEVOPS, "tool", ("kube netes",)),
    _t("kubectl", "kubectl", Domain.DEVOPS, "tool", ("kube control", "cube control", "tube control", "ubitil", "hubitel")),
    _t("docker", "Docker", Domain.DEVOPS, "tool"),
    _t("docker compose", "Docker Compose", Domain.DEVOPS, "tool"),
    _t("terraform", "Terraform", Domain.DEVOPS, "tool", ("terra form",)),
    _t("ansible", "Ansible", Domain.DEVOPS, "tool"),
    _t("prometheus", "Prometheus", Domain.DEVOPS, "tool"),
    _t("grafana", "Grafana", Domain.DEVOPS, "tool"),
    _t("nginx", "nginx", Domain.DEVOPS, "tool", ("engine x",)),
    _t("github actions", "GitHub Actions", Domain.DEVOPS, "phrase", ("git hub actions",)),
    _t("helm", "Helm", Domain.DEVOPS, "tool", (), AMB_ORDINARY),
    _t("argo cd", "ArgoCD", Domain.DEVOPS, "tool", ("argocd",)),
]

_WEB = [
    _t("fastapi", "FastAPI", Domain.DEVELOPER, "framework", ("fast api",)),
    _t("next js", "Next.js", Domain.DEVELOPER, "framework", ("nextjs", "next.js")),
    _t("react", "React", Domain.DEVELOPER, "framework", (), AMB_ORDINARY),
    _t("vue", "Vue.js", Domain.DEVELOPER, "framework", ("view", "vue js", "vuejs")),
    _t("django", "Django", Domain.DEVELOPER, "framework"),
    _t("flask", "Flask", Domain.DEVELOPER, "framework", (), AMB_ORDINARY),
    _t("express", "Express", Domain.DEVELOPER, "framework", (), AMB_ORDINARY),
    _t("tailwind", "Tailwind CSS", Domain.DEVELOPER, "framework", ("tailwindcss", "tailwind css")),
    _t("pydantic", "Pydantic", Domain.DEVELOPER, "library", ("pie dantic",)),
    _t("node js", "Node.js", Domain.DEVELOPER, "runtime", ("nodejs", "node.js")),
]

_DATABASES = [
    _t("postgresql", "PostgreSQL", Domain.DEVELOPER, "database",
       ("postgres", "post gres sql", "postgrey sql", "post dre sql", "postjsql")),
    _t("sqlalchemy", "SQLAlchemy", Domain.DEVELOPER, "library", ("sql alchemy",)),
    _t("mongodb", "MongoDB", Domain.DEVELOPER, "database", ("mongo db", "mongo")),
    _t("redis", "Redis", Domain.DEVELOPER, "database"),
    _t("elasticsearch", "Elasticsearch", Domain.DEVELOPER, "database", ("elastic search",)),
    _t("mysql", "MySQL", Domain.DEVELOPER, "database", ("my sql",)),
    _t("sqlite", "SQLite", Domain.DEVELOPER, "database", ("sql lite", "s q lite")),
]

_DATA_ENG = [
    _t("kafka", "Kafka", Domain.DATA_SCIENCE, "tool", (), AMB_PROPER),
    _t("rabbitmq", "RabbitMQ", Domain.DATA_SCIENCE, "tool", ("rabbit m q", "rabbit mq")),
    _t("spark", "Spark", Domain.DATA_SCIENCE, "tool", (), AMB_ORDINARY),
    _t("airflow", "Airflow", Domain.DATA_SCIENCE, "tool", ("air flow",)),
    _t("snowflake", "Snowflake", Domain.DATA_SCIENCE, "product", (), AMB_ORDINARY),
    _t("databricks", "Databricks", Domain.DATA_SCIENCE, "product", ("data bricks",)),
    _t("parquet", "Parquet", Domain.DATA_SCIENCE, "format"),
]

_ACADEMIC = [
    _t("arxiv", "arXiv", Domain.GENERAL, "platform", ("archive", "ar xiv")),
    _t("latex", "LaTeX", Domain.GENERAL, "format", ("lay tech", "lah tech")),
    _t("bibtex", "BibTeX", Domain.GENERAL, "format", ("bib tech",)),
    _t("doi", "DOI", Domain.GENERAL, "standard", ("d o i",)),
    _t("orcid", "ORCID", Domain.GENERAL, "standard", ("or kid",)),
]

# Python ecosystem (distinct from generic web). Canonicals are official casings.
_PYTHON = [
    _t("python", "Python", Domain.DEVELOPER, "language", (), AMB_ORDINARY),
    _t("django", "Django", Domain.DEVELOPER, "framework"),
    _t("flask", "Flask", Domain.DEVELOPER, "framework", (), AMB_ORDINARY),
    _t("fastapi", "FastAPI", Domain.DEVELOPER, "framework", ("fast api",)),
    _t("numpy", "NumPy", Domain.DEVELOPER, "library", ("num pie", "num py")),
    _t("pandas", "pandas", Domain.DEVELOPER, "library", (), AMB_ORDINARY),
    _t("scikit learn", "scikit-learn", Domain.DEVELOPER, "library", ("sklearn",)),
    _t("sqlalchemy", "SQLAlchemy", Domain.DEVELOPER, "library", ("sql alchemy",)),
    _t("pydantic", "Pydantic", Domain.DEVELOPER, "library", ("pie dantic",)),
    _t("pytest", "pytest", Domain.DEVELOPER, "library", ("pie test", "py test")),
    _t("poetry", "Poetry", Domain.DEVELOPER, "tool", (), AMB_ORDINARY),
    _t("uv", "uv", Domain.DEVELOPER, "tool", ("you vee",)),
]

# Cloud providers / services (devops_cloud group). Conservative aliases.
_CLOUD = [
    _t("aws", "AWS", Domain.DEVOPS, "platform", ("a w s", "amazon web services")),
    _t("azure", "Azure", Domain.DEVOPS, "platform", (), AMB_ORDINARY),
    _t("gcp", "GCP", Domain.DEVOPS, "platform", ("g c p", "google cloud")),
    _t("lambda", "Lambda", Domain.DEVOPS, "service", (), AMB_ORDINARY),
    _t("dynamodb", "DynamoDB", Domain.DEVOPS, "service", ("dynamo db", "dynamo")),
    _t("cloudformation", "CloudFormation", Domain.DEVOPS, "service", ("cloud formation",)),
    _t("s three", "S3", Domain.DEVOPS, "service", ("s 3", "s3")),
    _t("ec two", "EC2", Domain.DEVOPS, "service", ("ec 2", "ec2")),
]

DOMAIN_PACKS: Dict[str, List[DomainTerm]] = {
    "ai_ml": _AI_ML,
    "security": _SECURITY,
    "devops": _DEVOPS,
    "cloud": _CLOUD,
    "web": _WEB,
    "python": _PYTHON,
    "databases": _DATABASES,
    "data_engineering": _DATA_ENG,
    "academic": _ACADEMIC,
}


def pack_terms(domains: List[str] | None = None) -> List[KnowledgeTerm]:
    """Return KnowledgeTerms for the given domains (all if None), enabled only."""
    names = domains if domains is not None else list(DOMAIN_PACKS)
    out: List[KnowledgeTerm] = []
    for name in names:
        for dt in DOMAIN_PACKS.get(name, []):
            if dt.enabled:
                out.append(dt.to_knowledge_term())
    return out


def pack_stats() -> Dict[str, dict]:
    stats = {}
    for name, terms in DOMAIN_PACKS.items():
        stats[name] = {
            "term_count": len(terms),
            "ambiguous": sum(1 for t in terms if t.ambiguity_class != AMB_NONE),
            "official_canonical": sum(1 for t in terms if t.canonical_confidence >= CONF_OFFICIAL),
        }
    return stats


# --- canonicalization map (evidence-driven; NOT title-casing) --------------
# normalized spoken/lower form -> official canonical. Built from the packs so
# there is a single source of truth.
def canonical_map() -> Dict[str, str]:
    m: Dict[str, str] = {}
    for terms in DOMAIN_PACKS.values():
        for t in terms:
            m[t.spoken_form.lower()] = t.canonical_form
            m[t.canonical_form.lower()] = t.canonical_form
            for a in t.aliases:
                m[a.lower()] = t.canonical_form
    return m
