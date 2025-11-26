# Forward vs Inverse
On ne peut pas “juste” remplacer `forward()` par `inverse()` selon le mode. Les deux modes ne diffèrent pas seulement par **quelle fonction du convertisseur** on appelle, mais surtout par **qui décide du débit** (le bus amont ou le bus aval) et par **comment on pose les bornes**.

## Signes & conventions
- `bus.net_w > 0` : surplus (injection nette sur le bus)  
- `bus.net_w < 0` : déficit / demande (consommation nette sur le bus)  
- Un convertisseur `u -> v` avec rendement `η` vérifie:  
  `p_out = forward(p_in)` et `p_in = inverse(p_out)` (idéalement inverses l’une de l’autre).

## Mode “inverse” = la demande aval tire l’amont (pull)
Objectif : **annuler le déficit de v** en remontant la chaîne.

Pour chaque arête `(u -> v)` (ordre topo inversé) :
1) Mesure le **besoin** de `v`: `need_v = max(-net_w[v], 0)`.  
2) Fixe la **sortie** du convertisseur au besoin : `p_out = need_v`.  
3) Calcule **l’entrée requise** : `p_in = conv.inverse(p_out)`.  
4) Met à jour:
   - `net_w[u] -= p_in`  (l’amont “paye” le besoin)
   - `net_w[v] += p_out` (l’aval est soulagé)

👉 Ici, c’est **l’aval** qui fixe le débit. On “répercute” la demande jusqu’aux racines (où il restera typiquement un `net_w < 0` représentant le carburant à fournir).  
Note : on n’a pas borné par la disponibilité amont — volontaire : on veut que la demande “remonte” intégralement. C’est ce qui fait sens pour une chaîne où la source primaire est “illimitée” conceptuellement (réservoir de fuel, réseau, etc.), et on lit le besoin total à la racine.

## Mode “forward” = l’amont pousse vers l’aval (push)
Objectif : **écouler le surplus amont** pour **réduire** les déficits en aval.

Pour chaque arête `(u -> v)` (ordre topo) :
1) Mesure le **surplus dispo** à `u`: `avail_u = max(net_w[u], 0)`.  
2) Mesure le **besoin** à `v`: `need_v = max(-net_w[v], 0)`.  
3) Traduis le besoin en **entrée max** admissible : `p_in_cap = conv.inverse(need_v)`.  
4) Fixe l’**entrée utilisée** : `p_in_used = min(avail_u, p_in_cap)`.  
5) Déduit la **sortie produite** : `p_out = conv.forward(p_in_used)`.  
6) Met à jour:
   - `net_w[u] -= p_in_used` (on consomme le surplus amont)
   - `net_w[v] += p_out`     (on comble une partie du besoin aval)

👉 Ici, c’est **l’amont** qui propose un débit, **borné** par le besoin aval. On utilise **les deux** fonctions du convertisseur :  
- `inverse()` pour **convertir un besoin** en input-cap,  
- `forward()` pour **convertir l’input réel** en output.

## Pourquoi on ne peut pas “juste” switcher forward/inverse ?
Parce que le **débit cible** n’est pas le même objet dans les deux modes :
- en **inverse**, on choisit d’abord `p_out = need_v`, puis on calcule `p_in`.  
- en **forward**, on choisit d’abord `p_in_used = min(avail_u, p_in_cap)`, puis on calcule `p_out`.

Autrement dit, le **sens de causalité** change :
- inverse : **besoin aval ➜ input requis amont**, sans borne de disponibilité (la dette remonte) ;
- forward : **surplus amont ➜ output produit**, borné par le besoin aval (pas d’over-supply).

## Mini exemple numérique
Genset `Chemical -> Electrical` avec `η = 0.5`.  
État initial :  
- `net_w[Electrical] = -20` (demande de 20)  
- `net_w[Chemical] = 0`

**Inverse** :
- `need_v = 20` → `p_out = 20`  
- `p_in = 20 / 0.5 = 40`  
- maj : `net_w[Electrical] += 20 → 0`, `net_w[Chemical] -= 40 → -40`  
→ on lit à la racine chimique une “dette” de 40 (fuel à fournir).

**Forward** (supposons un surplus chimique de +30) :
- `avail_u = 30`, `need_v = 20`  
- `p_in_cap = inverse(20) = 40`  
- `p_in_used = min(30, 40) = 30`  
- `p_out = 30 * 0.5 = 15`  
- maj : `net_w[Chemical] -= 30 → 0`, `net_w[Electrical] += 15 → -5` (reste un déficit de 5)  
→ si un autre amont existe, il pourra compléter ; sinon, déficit résiduel.

## Quand choisir quel mode ?
- **Inverse** : tu imposes des **demandes** (profils de charge) et tu veux connaître **combien** la source primaire doit fournir (carburant, réseau, etc.). C’est le plus naturel pour bilaner une consommation.  
- **Forward** : tu imposes des **surpluses de production** (PV, éolien, etc.) ou des injections fixes et tu veux voir **combien** de demande tu couvres en aval.

Beaucoup de systèmes réels mélangent les deux (certaines injections imposées + certaines demandes imposées). On peut alors :
- faire des **passes** (push puis pull),  
- introduire des **priorités** sur les arêtes,  
- ou aller vers un solveur d’optimisation (LP/QP) si tu veux une allocation “globale optimale”.

---

> On peut faire une petite refacto pour factoriser le `if mode` en une fonction par arête (policy) — mais il y aura toujours deux politiques différentes, car la “variable pilotée” (p_out vs p_in) n’est pas la même.
