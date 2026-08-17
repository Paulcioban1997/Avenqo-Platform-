"""Familles d'intelligence artificielle orchestrées par l'AI Engine.

Chaque sous-dossier représente un problème métier (Forecasting, Recommendation,
Anomaly Detection, Synthetic Data, NLP, Vision, OCR, LLM, RAG, Audio) et partage la
même organisation :

    strategy.py   — branche le catalogue de la famille sur l'algorithme générique partagé
    trainer.py    — entraînement (délègue au candidat, identique à toutes les familles)
    optimizer.py  — point d'extension pour la recherche d'hyperparamètres
    evaluator.py  — évaluation (délègue au service d'évaluation partagé)
    candidates.py — construit les candidats disponibles à partir du registre
    registry.py   — catalogue des modèles utilisés par la famille
    models/       — UNIQUEMENT les modèles propres à cette famille (non réutilisés
                    ailleurs, ex : ARIMA pour Forecasting, BERT pour NLP). Ce dossier
                    est absent lorsqu'une famille réutilise exclusivement des
                    architectures partagées (ex : Vision, OCR, LLM, Audio).

Un modèle partagé entre plusieurs familles (LSTM, GNN, GAN, CTGAN, CNN, ResNet...) ne
vit jamais dans `models/` : il vit une seule fois sous
`shared.ai_engine.architectures`, et chaque `registry.py` qui en a besoin l'importe
directement — sans jamais le dupliquer.

Machine Learning et Deep Learning ne sont pas des familles métier mais de simples
catégories techniques : leur registre/stratégie vit directement sous
`shared.ai_engine.architectures.machine_learning` et
`shared.ai_engine.architectures.deep_learning`, sans dossier ici.

Ajouter une nouvelle famille métier ne nécessite jamais de modifier `AIEngine` : il
suffit de créer un nouveau dossier suivant cette organisation et de l'enregistrer dans
`shared.ai_engine.core.registry.build_default_execution_strategy_registry`.
"""
