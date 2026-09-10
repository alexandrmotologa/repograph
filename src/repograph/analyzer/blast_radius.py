"""Blast radius traversal and refactoring impact calculation engine."""

from collections import deque

import networkx as nx

from repograph.models import (
    BlastRadiusNode,
    BlastRadiusReport,
    ImpactCategory,
    SymbolKind,
)


class BlastRadiusCalculator:
    """Calculates upstream callers, downstream side effects, and refactoring risk scores."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def calculate(
        self,
        target_query: str,
        max_depth: int = 10,
    ) -> BlastRadiusReport:
        """Compute blast radius for a target symbol name or node ID."""
        target_id = self._resolve_target_id(target_query)
        if not target_id or not self.graph.has_node(target_id):
            return BlastRadiusReport(
                target_id=target_query,
                target_name=target_query,
                target_file="",
                score=0.0,
            )

        target_data = self.graph.nodes[target_id]
        target_name = target_data.get("name", target_id)
        target_file = target_data.get("file_path", "")

        # 1. Upstream Traversal (Who calls me / Who breaks if I change?)
        upstream_nodes = self._traverse_upstream(target_id, max_depth)

        # 2. Downstream Traversal (What do I call / What side effects do I trigger?)
        downstream_nodes = self._traverse_downstream(target_id, max_depth)

        # 3. Aggregate Affected Artifacts
        affected_files: set[str] = {target_file} if target_file else set()
        affected_entrypoints: set[str] = set()
        affected_tests: set[str] = set()

        for node in upstream_nodes:
            if node.file_path:
                affected_files.add(node.file_path)
            if node.category == ImpactCategory.CRITICAL:
                affected_entrypoints.add(f"{node.name} ({node.file_path})")
            elif node.category == ImpactCategory.TEST:
                affected_tests.add(f"{node.name} ({node.file_path})")

        for node in downstream_nodes:
            if node.file_path:
                affected_files.add(node.file_path)

        # 4. Calculate Quantified Risk Score (0.0 - 100.0)
        score = self._compute_risk_score(
            upstream_count=len(upstream_nodes),
            downstream_count=len(downstream_nodes),
            entrypoints_count=len(affected_entrypoints),
            affected_files_count=len(affected_files),
            tests_count=len(affected_tests),
        )

        total_impacted = len(upstream_nodes) + len(downstream_nodes)

        return BlastRadiusReport(
            target_id=target_id,
            target_name=target_name,
            target_file=target_file,
            score=score,
            upstream_callers=upstream_nodes,
            downstream_callees=downstream_nodes,
            affected_files=sorted(list(affected_files)),
            affected_entrypoints=sorted(list(affected_entrypoints)),
            affected_tests=sorted(list(affected_tests)),
            total_impacted_symbols=total_impacted,
        )

    def _resolve_target_id(self, target_query: str) -> str | None:
        """Find the matching node ID for a query string."""
        if self.graph.has_node(target_query):
            return target_query

        # Match by qualified_name exact or suffix
        query_clean = target_query.strip()
        candidates: list[str] = []

        for node_id, data in self.graph.nodes(data=True):
            if data.get("kind") == SymbolKind.MODULE.value:
                continue

            qual = data.get("qualified_name", "")
            name = data.get("name", "")

            if qual == query_clean or qual.endswith(f".{query_clean}"):
                candidates.append(node_id)
            elif name == query_clean:
                candidates.append(node_id)

        if candidates:
            # Return first or prioritize non-test candidate
            for c in candidates:
                if "test" not in self.graph.nodes[c].get("file_path", "").lower():
                    return c
            return candidates[0]

        return None

    def _traverse_upstream(self, target_id: str, max_depth: int) -> list[BlastRadiusNode]:
        """BFS backwards along incoming edges to find callers."""
        visited: dict[str, int] = {target_id: 0}
        parent_map: dict[str, str] = {}
        queue: deque[tuple[str, int]] = deque([(target_id, 0)])
        result: list[BlastRadiusNode] = []

        while queue:
            curr_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for pred_id in self.graph.predecessors(curr_id):
                edge_data = self.graph.get_edge_data(pred_id, curr_id) or {}
                edge_type = edge_data.get("edge_type", "")

                # Focus on CALLS and IMPORTS
                if edge_type in ("CALLS", "IMPORTS", "EXTENDS", "IMPLEMENTS"):
                    if pred_id not in visited:
                        visited[pred_id] = depth + 1
                        parent_map[pred_id] = curr_id
                        queue.append((pred_id, depth + 1))

                        node_data = self.graph.nodes[pred_id]
                        path = self._reconstruct_path(pred_id, target_id, parent_map)
                        category = self._categorize_node(pred_id, node_data)

                        result.append(
                            BlastRadiusNode(
                                node_id=pred_id,
                                name=node_data.get("name", pred_id),
                                kind=SymbolKind(node_data.get("kind", SymbolKind.FUNCTION.value)),
                                file_path=node_data.get("file_path", ""),
                                depth=depth + 1,
                                category=category,
                                path_from_target=path,
                            )
                        )

        result.sort(key=lambda n: (n.depth, n.name))
        return result

    def _traverse_downstream(self, target_id: str, max_depth: int) -> list[BlastRadiusNode]:
        """BFS forwards along outgoing edges to find side effects."""
        visited: dict[str, int] = {target_id: 0}
        parent_map: dict[str, str] = {}
        queue: deque[tuple[str, int]] = deque([(target_id, 0)])
        result: list[BlastRadiusNode] = []

        while queue:
            curr_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for succ_id in self.graph.successors(curr_id):
                edge_data = self.graph.get_edge_data(curr_id, succ_id) or {}
                edge_type = edge_data.get("edge_type", "")

                if edge_type in ("CALLS", "EXTENDS", "IMPLEMENTS"):
                    if succ_id not in visited:
                        visited[succ_id] = depth + 1
                        parent_map[succ_id] = curr_id
                        queue.append((succ_id, depth + 1))

                        node_data = self.graph.nodes[succ_id]
                        path = self._reconstruct_path(succ_id, target_id, parent_map)
                        category = self._categorize_node(succ_id, node_data)

                        result.append(
                            BlastRadiusNode(
                                node_id=succ_id,
                                name=node_data.get("name", succ_id),
                                kind=SymbolKind(node_data.get("kind", SymbolKind.FUNCTION.value)),
                                file_path=node_data.get("file_path", ""),
                                depth=depth + 1,
                                category=category,
                                path_from_target=path,
                            )
                        )

        result.sort(key=lambda n: (n.depth, n.name))
        return result

    def _categorize_node(self, node_id: str, node_data: dict) -> ImpactCategory:
        """Determine severity category for an impacted node."""
        file_path = node_data.get("file_path", "").lower()
        name = node_data.get("name", "").lower()
        is_entry = node_data.get("is_entrypoint", False)

        if "test" in file_path or name.startswith("test_"):
            return ImpactCategory.TEST

        if is_entry or any(
            kw in file_path for kw in ("controller", "route", "api", "cli", "handler")
        ):
            return ImpactCategory.CRITICAL

        if node_data.get("kind") in (SymbolKind.CLASS.value, SymbolKind.INTERFACE.value):
            return ImpactCategory.HIGH

        if any(kw in file_path for kw in ("service", "model", "domain", "repository")):
            return ImpactCategory.HIGH

        return ImpactCategory.MEDIUM

    def _reconstruct_path(
        self, start_id: str, end_id: str, parent_map: dict[str, str]
    ) -> list[str]:
        path = [start_id]
        curr = start_id
        while curr in parent_map and curr != end_id:
            curr = parent_map[curr]
            path.append(curr)
        return path

    def _compute_risk_score(
        self,
        upstream_count: int,
        downstream_count: int,
        entrypoints_count: int,
        affected_files_count: int,
        tests_count: int,
    ) -> float:
        """Calculate weighted impact score normalized between 0.0 and 100.0."""
        # High entrypoint presence significantly increases refactoring danger
        raw_score = (
            (upstream_count * 4.0)
            + (downstream_count * 1.5)
            + (entrypoints_count * 20.0)
            + (affected_files_count * 5.0)
        )

        # Dampen if adequate tests exist to catch regressions
        if tests_count > 0:
            test_factor = max(0.6, 1.0 - (tests_count * 0.08))
            raw_score *= test_factor
        else:
            # Penalty for untested affected code
            raw_score *= 1.25

        # Normalize with logarithmic dampening for very large numbers
        normalized = min(100.0, round(raw_score, 1))
        return max(1.0 if (upstream_count > 0 or downstream_count > 0) else 0.0, normalized)
