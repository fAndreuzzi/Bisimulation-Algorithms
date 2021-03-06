import networkx as nx
import pytest

from bisimulation_algorithms.utilities.rank_computation import (
    compute_rank,
)

from bisimulation_algorithms.dovier_piazza_policriti.graph_decorator import (
    prepare_graph,
)

from .wf_test_cases import graphs_wf_nwf


@pytest.mark.parametrize("graph, wf_nodes, nwf_nodes", graphs_wf_nwf)
def test_mark_wf_nodes_correct(graph, wf_nodes, nwf_nodes):
    vertexes = prepare_graph(graph)

    for i in range(len(graph.nodes)):
        assert (i in wf_nodes and vertexes[i].wf) or (
            i in nwf_nodes and not vertexes[i].wf
        )
