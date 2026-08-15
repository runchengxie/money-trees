from __future__ import annotations

import copy
import operator
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from moneytree.data import factor_columns as list_factor_columns
from moneytree.data import normalize_factor_prefixes


@dataclass
class ExprNode:
    value: object
    children: list[ExprNode] | None = None

    def __init__(self, value: object, children: list[ExprNode] | None = None) -> None:
        self.value = value
        self.children = children or []

    def __repr__(self) -> str:
        if not self.children:
            return str(self.value)
        return f"{self.value}{self.children}"


DEFAULT_CONSTANTS: tuple[int, ...] = (3, 5, 10, 20, 60)


def tree_to_formula(node: ExprNode) -> str:
    if not node.children:
        return str(node.value)
    args = [tree_to_formula(child) for child in node.children]
    if len(args) == 2 and node.value in {"+", "-", "*", "/"}:
        return f"({args[0]} {node.value} {args[1]})"
    return f"{node.value}({', '.join(args)})"


def get_tree_depth(node: ExprNode) -> int:
    if not node.children:
        return 1
    return 1 + max(get_tree_depth(child) for child in node.children)


def _safe(op: Any, a: Any, b: Any = None) -> Any:
    with np.errstate(divide="ignore", invalid="ignore"):
        result = op(a) if b is None else op(a, b)
    return result.replace([np.inf, -np.inf], np.nan)


def _op_add(a, b):
    return _safe(operator.add, a, b)


def _op_sub(a, b):
    return _safe(operator.sub, a, b)


def _op_mul(a, b):
    return _safe(operator.mul, a, b)


def _op_div(a, b):
    return _safe(operator.truediv, a, b)


def _op_neg(a):
    return _safe(operator.neg, a)


def _op_log(a):
    return _safe(np.log, np.abs(a) + 1e-6)


def _op_sqrt(a):
    return _safe(np.sqrt, np.abs(a))


def _op_cs_rank(a):
    return a.rank(axis=1, pct=True)


def _op_ts_delay(a, n):
    return a.shift(int(n))


def _op_ts_corr(a, b, n):
    return a.rolling(window=int(n)).corr(b).fillna(0)


def _op_ts_mean(a, n):
    return a.rolling(window=int(n)).mean().ffill()


def _op_ts_std(a, n):
    return a.rolling(window=int(n)).std().fillna(0)


def _op_ts_min(a, n):
    return a.rolling(window=int(n)).min().ffill()


def _op_ts_max(a, n):
    return a.rolling(window=int(n)).max().ffill()


def _op_ts_delta(a, n):
    return a.diff(int(n)).fillna(0)


_FUNCTION_SPECS = [
    ("+", _op_add, 2),
    ("-", _op_sub, 2),
    ("*", _op_mul, 2),
    ("/", _op_div, 2),
    ("neg", _op_neg, 1),
    ("log", _op_log, 1),
    ("sqrt", _op_sqrt, 1),
    ("cs_rank", _op_cs_rank, 1),
    ("ts_delay", _op_ts_delay, 2),
    ("ts_corr", _op_ts_corr, 3),
    ("ts_mean", _op_ts_mean, 2),
    ("ts_std", _op_ts_std, 2),
    ("ts_min", _op_ts_min, 2),
    ("ts_max", _op_ts_max, 2),
    ("ts_delta", _op_ts_delta, 2),
]

FUNCTION_MAP = {name: (func, arity) for name, func, arity in _FUNCTION_SPECS}

_PARAM_FUNCTIONS = frozenset({"ts_delay", "ts_corr", "ts_mean", "ts_std", "ts_min", "ts_max", "ts_delta"})


def _random_terminal(rng: random.Random, terminals: Sequence[tuple[object, bool]]) -> object:
    return rng.choice([term[0] for term in terminals])


def _random_parameter(rng: random.Random, terminals: Sequence[tuple[object, bool]]) -> object:
    const_terminals = [term[0] for term in terminals if term[1]]
    if not const_terminals:
        return rng.choice(DEFAULT_CONSTANTS)
    return rng.choice(const_terminals)


def grow_tree(
    max_depth: int,
    terminals: Sequence[tuple[object, bool]],
    rng: random.Random,
    current_depth: int = 0,
) -> ExprNode:
    if current_depth == max_depth - 1 or rng.random() < 0.3:
        return ExprNode(_random_terminal(rng, terminals))
    func_name, _, arity = rng.choice(_FUNCTION_SPECS)
    children = [
        grow_tree(max_depth, terminals, rng, current_depth + 1) for _ in range(arity)
    ]
    if func_name in _PARAM_FUNCTIONS:
        children[-1] = ExprNode(_random_parameter(rng, terminals))
    return ExprNode(func_name, children)


def full_tree(
    max_depth: int,
    terminals: Sequence[tuple[object, bool]],
    rng: random.Random,
    current_depth: int = 0,
) -> ExprNode:
    if current_depth == max_depth - 1:
        non_const = [term[0] for term in terminals if not term[1]]
        value = rng.choice(non_const) if non_const else _random_terminal(rng, terminals)
        return ExprNode(value)
    func_name, _, arity = rng.choice(_FUNCTION_SPECS)
    children = [
        full_tree(max_depth, terminals, rng, current_depth + 1) for _ in range(arity)
    ]
    if func_name in _PARAM_FUNCTIONS:
        children[-1] = ExprNode(_random_parameter(rng, terminals))
    return ExprNode(func_name, children)


def initialize_population(
    pop_size: int,
    max_depth: int,
    terminals: Sequence[tuple[object, bool]],
    rng: random.Random,
) -> list[ExprNode]:
    population: list[ExprNode] = []
    for idx in range(pop_size):
        depth = rng.randint(2, max_depth)
        if idx < pop_size / 2:
            population.append(grow_tree(depth, terminals, rng))
        else:
            population.append(full_tree(depth, terminals, rng))
    return population


def get_all_nodes(root: ExprNode) -> list[ExprNode]:
    nodes = [root]
    for child in root.children:
        nodes.extend(get_all_nodes(child))
    return nodes


_PANEL_FUNCTIONS = frozenset({"cs_rank", "ts_delay", "ts_corr", "ts_mean", "ts_std", "ts_min", "ts_max", "ts_delta"})


def _panel_arg(value: Any, template: pd.DataFrame) -> Any:
    if isinstance(value, pd.DataFrame):
        return value
    return pd.DataFrame(0, index=template.index, columns=template.columns)


def evaluate_expression(expr: ExprNode, data: dict[str, pd.DataFrame]) -> Any:
    if not expr.children:
        if isinstance(expr.value, str) and expr.value in data:
            return data[expr.value]
        return expr.value
    child_values = [evaluate_expression(child, data) for child in expr.children]
    func_name = expr.value
    if func_name not in FUNCTION_MAP:
        raise ValueError(f"Unknown function: {func_name}")
    func, arity = FUNCTION_MAP[func_name]
    if len(child_values) != arity:
        raise ValueError(
            f"Function '{func_name}' expects {arity} arguments, got {len(child_values)}"
        )
    if func_name in _PARAM_FUNCTIONS and not isinstance(child_values[-1], int):
        template = next(item for item in child_values if isinstance(item, pd.DataFrame))
        return pd.DataFrame(0, index=template.index, columns=template.columns)
    if func_name in _PANEL_FUNCTIONS:
        template = next((item for item in child_values if isinstance(item, pd.DataFrame)), None)
        if template is None:
            return 0.0
        if func_name in _PARAM_FUNCTIONS:
            child_values = [
                _panel_arg(value, template) if idx < arity - 1 else value
                for idx, value in enumerate(child_values)
            ]
        else:
            child_values = [_panel_arg(value, template) for value in child_values]
    return func(*child_values)


def fitness_function(
    expr: ExprNode,
    data: dict[str, pd.DataFrame],
    complexity_penalty: float,
) -> float:
    try:
        factor_values = evaluate_expression(expr, data)
        if not isinstance(factor_values, pd.DataFrame):
            return 0.0
        stacked = factor_values.stack()
        if stacked.isnull().all() or stacked.std() < 1e-6:
            return 0.0
        future = data["future_returns"]
        aligned_factor, aligned_returns = factor_values.align(future, join="inner", axis=0)
        factor_flat = aligned_factor.stack()
        returns_flat = aligned_returns.stack()
        if len(factor_flat) < 100:
            return 0.0
        ic, _ = spearmanr(factor_flat.fillna(0), returns_flat.fillna(0))
        if np.isnan(ic):
            return 0.0
        penalty = complexity_penalty * get_tree_depth(expr)
        return abs(ic) - penalty
    except (ValueError, TypeError, ZeroDivisionError, IndexError, AttributeError):
        return 0.0


def tournament_selection(
    evaluated_population: Sequence[tuple[ExprNode, float]],
    tournament_size: int,
    rng: random.Random,
) -> ExprNode:
    tournament = rng.sample(evaluated_population, tournament_size)
    winner = max(tournament, key=lambda item: item[1])
    return winner[0]


def crossover(parent1: ExprNode, parent2: ExprNode, rate: float, rng: random.Random) -> tuple[ExprNode, ExprNode]:
    if rng.random() > rate:
        return parent1, parent2
    p1_nodes = get_all_nodes(parent1)
    p2_nodes = get_all_nodes(parent2)
    node1 = rng.choice(p1_nodes)
    node2 = rng.choice(p2_nodes)
    node1.value, node2.value = node2.value, node1.value
    node1.children, node2.children = node2.children, node1.children
    return parent1, parent2


def mutate(
    individual: ExprNode,
    terminals: Sequence[tuple[object, bool]],
    rate: float,
    rng: random.Random,
) -> ExprNode:
    if rng.random() > rate:
        return individual
    target_node = rng.choice(get_all_nodes(individual))
    if target_node.children:
        current_arity = len(target_node.children)
        compatible = [spec for spec in _FUNCTION_SPECS if spec[2] == current_arity]
        if compatible:
            target_node.value = rng.choice(compatible)[0]
    else:
        is_const_node = isinstance(target_node.value, int)
        if is_const_node:
            target_node.value = _random_parameter(rng, terminals)
        else:
            non_const = [term[0] for term in terminals if not term[1]]
            target_node.value = rng.choice(non_const) if non_const else _random_terminal(rng, terminals)
    return individual


def create_new_generation(
    evaluated_pop: Sequence[tuple[ExprNode, float]],
    terminals: Sequence[tuple[object, bool]],
    *,
    elitism_rate: float,
    crossover_rate: float,
    mutation_rate: float,
    tournament_size: int,
    rng: random.Random,
) -> list[ExprNode]:
    new_pop: list[ExprNode] = []
    elite_size = int(len(evaluated_pop) * elitism_rate)
    new_pop.extend([individual for individual, _ in evaluated_pop[:elite_size]])
    while len(new_pop) < len(evaluated_pop):
        parent1 = tournament_selection(evaluated_pop, tournament_size, rng)
        parent2 = tournament_selection(evaluated_pop, tournament_size, rng)
        child1, child2 = crossover(
            copy.deepcopy(parent1), copy.deepcopy(parent2), crossover_rate, rng
        )
        child1 = mutate(child1, terminals, mutation_rate, rng)
        child2 = mutate(child2, terminals, mutation_rate, rng)
        new_pop.extend([child1, child2])
    return new_pop[: len(evaluated_pop)]


def _neutralize(factor_values: pd.DataFrame, market_cap: pd.DataFrame) -> pd.DataFrame:
    neutralized = pd.DataFrame(np.nan, index=factor_values.index, columns=factor_values.columns)
    for date in factor_values.index:
        if date not in market_cap.index:
            continue
        y = factor_values.loc[date].dropna()
        x_mc = np.log(market_cap.loc[date].reindex(y.index)).dropna()
        common = y.index.intersection(x_mc.index)
        if len(common) < 2:
            continue
        y = y[common]
        x = x_mc[common]
        design = np.vstack([np.ones(len(x)), x]).T
        try:
            beta = np.linalg.inv(design.T @ design) @ design.T @ y
            residuals = y - design @ beta
            neutralized.loc[date, residuals.index] = residuals
        except np.linalg.LinAlgError:
            neutralized.loc[date, y.index] = y
    return neutralized.astype(float)


def post_process(
    best_expr: ExprNode,
    test_data: dict[str, pd.DataFrame],
    *,
    neutralize_with_cap: bool = False,
) -> dict[str, Any]:
    factor_values = evaluate_expression(best_expr, test_data)
    if not isinstance(factor_values, pd.DataFrame):
        return {"error": "无法在测试集上计算因子值"}

    neutralized = (
        _neutralize(factor_values, test_data["total_mv"]) if neutralize_with_cap else factor_values
    )
    future = test_data["future_returns"]
    aligned_factor, aligned_returns = factor_values.align(future, join="inner", axis=0)
    ic_series = aligned_factor.corrwith(aligned_returns, axis=1, method="spearman")
    ic_mean = float(ic_series.mean())
    ic_std = float(ic_series.std())
    icir = ic_mean / ic_std if ic_std > 0 else 0.0

    quantile_returns: list[pd.Series] = []
    for date in neutralized.index:
        factor_slice = neutralized.loc[date].dropna()
        if date not in future.index:
            continue
        return_slice = future.loc[date].reindex(factor_slice.index)
        if len(factor_slice) < 10:
            continue
        try:
            groups = pd.qcut(factor_slice, 5, labels=False, duplicates="drop")
            group_return = return_slice.groupby(groups).mean()
            quantile_returns.append(group_return)
        except (ValueError, IndexError):
            continue

    if not quantile_returns:
        quantiles = "分组回测失败"
    else:
        quantiles = pd.DataFrame(quantile_returns).mean().to_dict()

    return {
        "expression": tree_to_formula(best_expr),
        "ic_mean": ic_mean,
        "ic_std": ic_std,
        "icir": icir,
        "quantile_returns": quantiles,
    }


def build_terminals(factor_names: Sequence[str]) -> list[tuple[object, bool]]:
    terminals: list[tuple[object, bool]] = [(name, False) for name in factor_names]
    terminals.extend([(constant, True) for constant in DEFAULT_CONSTANTS])
    return terminals


def _to_wide(series: pd.Series) -> pd.DataFrame:
    name = series.name
    frame = series.reset_index()
    return frame.pivot(index="date", columns="ticker", values=name)


def prepare_mining_data(
    panel: pd.DataFrame,
    factor_names: Sequence[str],
    *,
    future_return_period: int = 5,
    close_column: str = "close_adj",
    cap_column: str = "total_mv",
) -> dict[str, pd.DataFrame]:
    """Pivot selected factor columns and build future-return/total-mv wide frames."""
    indexed = panel.set_index(["date", "ticker"]) if {"date", "ticker"}.issubset(panel.columns) else panel
    indexed = indexed.sort_index()

    if close_column not in indexed.columns:
        close_column = "close" if "close" in indexed.columns else None
    if close_column is None:
        raise ValueError("Mining requires a close or close_adj column to build forward returns.")
    close = indexed[close_column].astype(float)
    future_returns = (
        close.groupby(level="ticker", sort=False).shift(-int(future_return_period)) / close - 1
    )
    future_returns.name = "future_returns"

    data: dict[str, pd.DataFrame] = {}
    missing = [name for name in factor_names if name not in indexed.columns]
    if missing:
        raise ValueError(f"Requested factor columns are missing from the panel: {missing}")
    for name in factor_names:
        data[name] = _to_wide(indexed[name])

    data["future_returns"] = _to_wide(future_returns)
    if cap_column in indexed.columns:
        data["total_mv"] = _to_wide(indexed[cap_column].astype(float))
    elif "circ_mv" in indexed.columns:
        data["total_mv"] = _to_wide(indexed["circ_mv"].astype(float))
    return data


def run_mining(
    panel: pd.DataFrame,
    factor_names: Sequence[str],
    *,
    future_return_period: int = 5,
    pop_size: int = 100,
    max_gen: int = 20,
    max_depth: int = 4,
    seed: int = 42,
    complexity_penalty: float = 0.001,
    crossover_rate: float = 0.9,
    mutation_rate: float = 0.15,
    elitism_rate: float = 0.1,
    tournament_size: int = 5,
    close_column: str = "close_adj",
    cap_column: str = "total_mv",
    test_panel: pd.DataFrame | None = None,
    neutralize: bool = False,
) -> dict[str, Any]:
    """Run genetic-programming factor mining over selected alpha factor terminals.

    When ``test_panel`` is provided, the best discovered expression is validated
    out-of-sample with IC/ICIR/quantile returns and included in the returned report.
    """
    rng = random.Random(seed)
    data = prepare_mining_data(
        panel,
        factor_names,
        future_return_period=future_return_period,
        close_column=close_column,
        cap_column=cap_column,
    )
    terminals = build_terminals(factor_names)
    population = initialize_population(pop_size, max_depth, terminals, rng)

    best_individual: ExprNode | None = None
    best_fitness = -1.0
    fitness_history: list[float] = []
    generations: list[dict[str, Any]] = []

    for gen in range(max_gen + 1):
        evaluated = sorted(
            ((individual, fitness_function(individual, data, complexity_penalty)) for individual in population),
            key=lambda item: item[1],
            reverse=True,
        )
        best_individual_gen, best_fitness_gen = evaluated[0]
        fitness_history.append(best_fitness_gen)
        if best_fitness_gen > best_fitness:
            best_fitness = best_fitness_gen
            best_individual = copy.deepcopy(best_individual_gen)
        generations.append(
            {
                "generation": gen,
                "best_fitness": best_fitness_gen,
                "avg_fitness": float(np.mean([fitness for _, fitness in evaluated])),
                "best_expression": tree_to_formula(best_individual_gen),
            }
        )
        if gen >= max_gen:
            break
        if len(fitness_history) > 10 and abs(best_fitness_gen - fitness_history[-11]) < 0.001:
            break
        population = create_new_generation(
            evaluated,
            terminals,
            elitism_rate=elitism_rate,
            crossover_rate=crossover_rate,
            mutation_rate=mutation_rate,
            tournament_size=tournament_size,
            rng=rng,
        )

    if best_individual is None:
        return {"error": "未能找到任何有效的因子", "generations": generations}

    report: dict[str, Any] = {
        "best_expression": tree_to_formula(best_individual),
        "best_fitness": best_fitness,
        "terminals": list(factor_names),
        "future_return_period": int(future_return_period),
        "generations": generations,
    }

    if test_panel is not None and len(test_panel):
        test_data = prepare_mining_data(
            test_panel,
            factor_names,
            future_return_period=future_return_period,
            close_column=close_column,
            cap_column=cap_column,
        )
        report["test"] = post_process(
            best_individual,
            test_data,
            neutralize_with_cap=bool(neutralize),
        )
    return report


def resolve_factor_names(
    columns: Iterable[object],
    *,
    factor_prefixes: Iterable[str] | None = None,
    factor_columns: Iterable[str] | None = None,
) -> list[str]:
    """Resolve mining terminals from the available panel columns."""
    column_names = [str(column) for column in columns]
    if factor_columns:
        explicit = [column for column in factor_columns if column in column_names]
        missing = [column for column in factor_columns if column not in column_names]
        if missing:
            raise ValueError(f"Requested factor columns are missing from the panel: {missing}")
        return explicit
    if factor_prefixes:
        prefixes = normalize_factor_prefixes(factor_prefixes)
        selected = [column for column in column_names if any(column.startswith(p) for p in prefixes)]
        if not selected:
            raise ValueError(
                f"No factor columns found for prefixes: {', '.join(prefixes)}."
            )
        return selected
    selected = list_factor_columns(column_names)
    if not selected:
        raise ValueError("No alpha factor columns found in the panel. Use --factor-prefixes or --factor-column.")
    return selected
