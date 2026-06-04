# Forward vs inverse

Le solveur DAG peut représenter les convertisseurs dans leur sens physique
`from_bus -> to_bus`, mais le mode de calcul détermine dans quel sens on utilise
cette chaîne.

Le mode recommandé dans l'état actuel du modèle est `inverse`. Le mode `forward`
existe dans la structure du code, mais il n'est pas encore le mode de référence
validé pour les exemples métier.

## Conventions

Dans le solveur, chaque bus porte un bilan instantané `net_w` en watts :

- `net_w > 0` : surplus ou injection nette sur le bus ;
- `net_w < 0` : déficit, demande ou consommation nette ;
- `net_w = 0` : bus équilibré.

Un convertisseur déclaré de `u` vers `v` suit le sens physique :

```text
u --convertisseur--> v
```

Avec un rendement constant `eta` :

```text
forward(p_in) = p_in * eta
inverse(p_out) = p_out / eta
```

Le YAML garde toujours le sens physique du convertisseur. C'est le mode du
solveur qui décide comment ce convertisseur est parcouru pendant le calcul.

## Mode inverse

Le mode `inverse` part d'une demande aval et remonte vers l'amont.

Il répond à la question :

```text
Quelle puissance faut-il fournir en amont pour satisfaire cette demande en aval ?
```

Pour chaque convertisseur `u -> v`, le solveur :

1. regarde le déficit du bus aval `v` ;
2. impose la sortie du convertisseur pour combler ce déficit ;
3. calcule l'entrée nécessaire avec `inverse()` ;
4. ajoute cette demande sur le bus amont `u`.

Dans ce mode, c'est donc l'aval qui fixe le débit.

## Mode forward

Le mode `forward` part d'un surplus amont et pousse vers l'aval.

Il répond à la question :

```text
Quelle partie de la demande aval peut être couverte par le surplus disponible en amont ?
```

Pour chaque convertisseur `u -> v`, le solveur :

1. regarde le surplus disponible sur le bus amont `u` ;
2. regarde le déficit du bus aval `v` ;
3. limite le débit à ce qui est utile pour l'aval ;
4. calcule la sortie avec `forward()`.

Dans ce mode, c'est donc l'amont qui propose le débit, borné par le besoin aval.

## Exemple numérique simple

On considère un groupe électrogène avec un rendement de `0.5`.

```text
fuel_bus --genset eta=0.5--> electrical_bus
```

La relation physique est :

```text
p_elec = p_fuel * 0.5
p_fuel = p_elec / 0.5
```

### Cas inverse

Situation initiale :

```text
fuel_bus       net_w = 0 W
electrical_bus net_w = -20 W
```

Le bus électrique a une demande de `20 W`.

Étapes de calcul :

1. Le besoin aval vaut `20 W`.
2. Le solveur impose `p_out = 20 W` sur la sortie du groupe.
3. Le groupe calcule l'entrée nécessaire :

```text
p_in = p_out / eta = 20 / 0.5 = 40 W
```

4. Les bus sont mis à jour :

```text
electrical_bus : -20 + 20 = 0 W
fuel_bus       : 0 - 40 = -40 W
```

Résultat :

```text
electrical_bus est équilibré
fuel_bus indique une demande de 40 W de puissance chimique
```

Ce mode est adapté si l'on impose des charges ou une mission et que l'on veut
calculer la puissance amont nécessaire.

### Cas forward

Situation initiale :

```text
fuel_bus       net_w = +30 W
electrical_bus net_w = -20 W
```

Le bus fuel dispose d'un surplus de `30 W`. Le bus électrique demande `20 W`.

Étapes de calcul :

1. Le surplus amont vaut `30 W`.
2. Le besoin aval vaut `20 W`.
3. Pour satisfaire totalement `20 W` en aval, il faudrait :

```text
p_in_needed = 20 / 0.5 = 40 W
```

4. Mais l'amont ne dispose que de `30 W`, donc :

```text
p_in_used = min(30, 40) = 30 W
```

5. La sortie réellement produite vaut :

```text
p_out = 30 * 0.5 = 15 W
```

6. Les bus sont mis à jour :

```text
fuel_bus       : +30 - 30 = 0 W
electrical_bus : -20 + 15 = -5 W
```

Résultat :

```text
fuel_bus n'a plus de surplus
electrical_bus garde un déficit de 5 W
```

Ce mode est adapté si l'on impose une production ou une injection amont et que
l'on veut savoir quelle partie des besoins aval est couverte.

## Exemple sur deux convertisseurs

On considère une chaîne :

```text
fuel_bus --genset eta=0.5--> electrical_bus --motor eta=0.8--> shaft_bus
```

### Inverse avec une demande mécanique

Situation initiale :

```text
shaft_bus      net_w = -16 W
electrical_bus net_w = 0 W
fuel_bus       net_w = 0 W
```

Calcul sur le moteur :

```text
besoin shaft = 16 W
besoin électrique = 16 / 0.8 = 20 W

shaft_bus      : -16 + 16 = 0 W
electrical_bus : 0 - 20 = -20 W
```

Calcul sur le groupe :

```text
besoin électrique = 20 W
besoin fuel = 20 / 0.5 = 40 W

electrical_bus : -20 + 20 = 0 W
fuel_bus       : 0 - 40 = -40 W
```

Résultat final :

```text
shaft_bus      = 0 W
electrical_bus = 0 W
fuel_bus       = -40 W
```

La demande mécanique de `16 W` implique donc `40 W` de puissance chimique amont.

### Forward avec une puissance fuel disponible

Situation initiale :

```text
fuel_bus       net_w = +40 W
electrical_bus net_w = 0 W
shaft_bus      net_w = -16 W
```

Ce cas illustre pourquoi le mode `forward` est moins direct pour les scénarios de
demande imposée. Le bus électrique n'a pas de déficit initial ; la demande est
plus loin, sur le bus mécanique.

Pour propager correctement le surplus jusqu'au shaft, il faut une logique de
besoins aval, de priorités ou de passes de calcul. C'est précisément ce qui rend
le mode `forward` plus délicat à valider dans l'architecture actuelle.

Dans les scénarios CGN documentés, on part généralement d'une vitesse, d'une
puissance arbre ou d'une charge électrique imposée. Le mode `inverse` correspond
donc mieux à l'usage principal : il remonte naturellement les besoins jusqu'aux
sources amont.

## Résumé

| Sujet | Mode inverse | Mode forward |
| --- | --- | --- |
| Question posée | Combien faut-il en amont ? | Que couvre le surplus amont ? |
| Débit piloté par | Besoin aval | Surplus amont |
| Fonction centrale | `inverse(p_out)` | `forward(p_in)` |
| Usage naturel | Bilan de consommation | Propagation de production disponible |
| État actuel | Mode recommandé | Présent mais non validé comme référence |

