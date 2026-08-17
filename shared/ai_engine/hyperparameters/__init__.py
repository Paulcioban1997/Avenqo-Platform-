"""Source unique de vérité pour tous les espaces d'hyperparamètres de l'AI Engine.

Aucune grille GridSearchCV/RandomizedSearchCV, ni aucun espace Optuna/KerasTuner,
ne doit être défini ailleurs dans le projet. `modules/*/training_specs.py` ne
décrit que la tâche métier (alias de colonnes, modèles autorisés, famille) et
importe ses estimateurs/grilles depuis ce paquet.
"""
