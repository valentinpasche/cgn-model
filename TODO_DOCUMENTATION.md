# TODO Documentation

Ambiguites restantes a documenter sans modifier le comportement numerique.

## Conventions physiques

- Preciser le sens metier exact des bus `from_bus` et `to_bus` pour chaque
  chaine energetique de reference. Le code les utilise comme sens nominal du
  convertisseur, mais la convention physique complete doit etre validee cote
  metier.
- Clarifier l'interpretation des `carrier` (`Electrical`, `Mechanical`,
  `Chemical`) au-dela de l'unite canonique actuelle [W].
- Documenter explicitement que le mode solver `forward` est present dans la
  structure mais marque non verifie dans `run_vector`.

## Coefficients et domaines de validite

- Renseigner l'origine des coefficients polynomiaux utilises pour les adapters
  vitesse -> puissance, vitesse -> force, vitesse -> eta et puissance ->
  puissance.
- Preciser pour chaque jeu de coefficients l'unite d'entree attendue, l'unite
  de sortie, la plage de validite et les hypotheses d'essai/calibration.
- Indiquer si les clips a 0 sur certains adapters representent une hypothese
  physique, un garde-fou numerique ou une convention de post-traitement.

## Navigation et profils de vitesse

- Confirmer les hypotheses MRUA utilisees pour les profils de vitesse :
  acceleration/deceleration constantes, repere longitudinal, absence de courant
  et absence de correction de manoeuvre.
- Clarifier la politique de retard : quand un retard est reporte, quand il est
  rattrape sur les pauses et quelle interpretation operationnelle donner aux
  secondes supprimees.
- Preciser si les horaires sont toujours interpretes comme heures locales
  naives sans date civile.

## Stockages et vecteurs energetiques

- Documenter les conventions de signe attendues pour les bus de stockage :
  stockage qui se remplit vs stockage qui se vide.
- Valider les conventions de PCI massique/volumique pour chaque vecteur
  energetique nomme (`diesel`, `H2`, batterie, etc.) et leur lien avec les
  densites.

## Verification

- Les fichiers sous `tests/` ressemblent partiellement a des scripts de
  validation manuelle. Ajouter, dans une passe separee, des assertions pytest
  couvrant les sorties numeriques de reference avant de refactorer davantage la
  documentation.
- L'environnement shell courant ne fournit pas `python` ni `git`; la verification
  automatique complete doit etre relancee dans l'environnement Conda du projet.
