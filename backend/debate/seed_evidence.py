"""
Default evidence and factual corpus for ChromaDB RAG in Argus AI Debate Platform.
"""

DEFAULT_EVIDENCE_CORPUS = [
    # AI Regulation & Ethics
    {
        "text": "The EU Artificial Intelligence Act (2024) categorizes AI systems into four risk levels and mandates strict audits, transparency, and human oversight for high-risk biometric and critical infrastructure deployment.",
        "metadata": {"topic": "AI Regulation", "category": "Law & Policy", "source": "European Union Legislation 2024", "stance": "pro"}
    },
    {
        "text": "Over-regulation of foundational open-source AI models risks stifling open academic research and technological innovation, concentrating market dominance among a small cartel of tech monopolies.",
        "metadata": {"topic": "AI Regulation", "category": "Economics & Tech", "source": "AI Open Source Policy Report", "stance": "con"}
    },
    {
        "text": "According to the Stanford AI Index Report 2024, corporate investment in generative AI reached $67 billion in 2023, with privacy breaches and automated deepfakes cited as primary enterprise risks.",
        "metadata": {"topic": "AI Regulation", "category": "Statistics", "source": "Stanford AI Index 2024", "stance": "neutral"}
    },
    
    # Ancient History / Classical Civilizations (e.g. Athens vs. Sparta)
    {
        "text": "Classical Athens established democratic assembly (Eklesia) and trial by jury under Cleisthenes in 508 BCE, laying the foundational political principles for modern Western constitutional democracies.",
        "metadata": {"topic": "Athens vs Sparta", "category": "History", "source": "Thucydides, History of Peloponnesian War", "stance": "pro"}
    },
    {
        "text": "The Spartan Agoge system prioritized martial discipline, civic equality among Equals (Homoioi), and military readiness, successfully resisting Persian invasion forces at Thermopylae in 480 BCE.",
        "metadata": {"topic": "Athens vs Sparta", "category": "History", "source": "Xenophon, Constitution of the Lacedaemonians", "stance": "con"}
    },

    # Universal Basic Income & Economy
    {
        "text": "The Finnish Universal Basic Income experiment (2017-2018) conducted on 2,000 unemployed individuals demonstrated improved psychological well-being, trust in institutions, and lower stress levels without reducing workforce participation.",
        "metadata": {"topic": "Universal Basic Income", "category": "Economics", "source": "Kela Finnish UBI Study 2020", "stance": "pro"}
    },
    {
        "text": "Funding an unconditional $1,000 monthly basic income for all US adults would require over $3.1 trillion annually—equivalent to more than 75% of total federal tax revenue.",
        "metadata": {"topic": "Universal Basic Income", "category": "Fiscal Policy", "source": "Tax Foundation Economic Model", "stance": "con"}
    },

    # Renewable Energy & Climate Action
    {
        "text": "The International Renewable Energy Agency (IRENA) 2023 report confirmed that 86% of newly commissioned utility-scale renewable power generation capacity had lower electricity costs than the cheapest fossil-fuel alternative.",
        "metadata": {"topic": "Renewable Energy", "category": "Energy & Climate", "source": "IRENA Renewable Power Generation Costs 2023", "stance": "pro"}
    },
    {
        "text": "Grid instability and battery storage shortages remain key hurdles for 100% intermittent solar and wind grids without reliable base-load generation like modern nuclear or geothermal energy.",
        "metadata": {"topic": "Renewable Energy", "category": "Infrastructure", "source": "IEA Electricity Market Report", "stance": "con"}
    },

    # Remote Work vs Office Work
    {
        "text": "A 2023 Stanford University randomized trial by Nick Bloom found that hybrid and fully remote work models improved employee retention by 35% without degrading objective worker productivity metrics.",
        "metadata": {"topic": "Remote Work", "category": "Workplace Economics", "source": "Stanford Working From Home Study 2023", "stance": "pro"}
    },
    {
        "text": "In-person collaboration fosters spontaneous innovation, informal mentoring, and stronger organizational social capital, as shown in MIT Media Lab studies on workplace proximity.",
        "metadata": {"topic": "Remote Work", "category": "Organizational Psychology", "source": "MIT Media Lab Collaboration Study", "stance": "con"}
    }
]
