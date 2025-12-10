# CGN - Modèle de simulation chaîne énergétique

---

## 🔧 Installation

### Via le fichier `environment.yml` (à privilégier, essentiellement)

> 1. Cloner le dépôt GitHub
> 2. En ligne de commande (conda) : se placer à la racine du repo, là où se trouve le fichier `environment.yml`
> 3. Executer les commandes suivantes :

```bash
conda env create -f environment.yml
conda activate cgnmodel
python -c "import cgn_model; print('OK:', cgn_model.__name__, 'version:', getattr(cgn_model, '__version__', '?'))"
```

## ▶️ Utilisation classique, via Spyder

Lancer l'application spyder depuis l'environnement **cgnmodel**

```bash
conda activate cgnmodel
spyder
```

Ou directement l'application de bureau : *Spyder 6 (cgnmodel)*

---

### *Objectifs - à faire*

## Inputs Romain - 26.11.2025

- Point d'entrée de toutes les valeurs via le/les fichiers YAML.  
But : Pas de valeurs à rentrer manuellement dans le code.

- Intégrer les valeurs limites des composants (convertisseurs).  
But : Pouvoir renseigner des valeurs maximales et avoir des seuil (e.g. puissance max.).

- Ajouter dans le contrat du bus l'unité physique du vecteur. Aussi pour les covertisseurs ?  
But : Normaliser les unités.

- Intéger un nouveau type de composant **Stockage**  
But : Avoir des des graphiques à la fin du calcul et *automatiser* le calcul.

- Objet **Bateau** qui conteint des équipements en fonction de son *type* (e.g. type de propulsion).

- Faire la documentations du code.


## Besoins CGN (Zoé) et but du code - Inputs Zoé - 27.11.2025

### Evaluer l'exploitation en terme de :

- Heures de fonctionnement
- Heures de ravitaillement
- Consomation (volume/masse)

### Comparer des architectures (énergétiques)

- Consomation journalière
- Poids et volume du réservoir/stockage (de l'objet physique pas de ce qu'il y a dedans)
- Durée du remplissage/recharge, lié au *débit* de recharge.

### Priorité, gestion des :

- Profils d'utilisation
- Architecture bateaux
- Vecteurs énergétique

# Je veux faire aussi

*Intégré dans les demandes ci-dessus*

- Un objet **course** qui appelle un profil de vitesse en fonction du **N°** de la course.