import networkx as nx
from bisimulation_algorithms.utilities.graph_entities import (
    _Vertex,
    _QBlock as _Block,
    _Edge,
    _Count,
    _XBlock,
    _SCC,
)
from typing import List, Tuple, Set, Dict
from .ranked_pta import ranked_split
from bisimulation_algorithms.paige_tarjan.pta import pta
from bisimulation_algorithms.dovier_piazza_policriti.graph_decorator import (
    build_vertexes_image,
)
from bisimulation_algorithms.dovier_piazza_policriti.fba import (
    build_block_counterimage,
)
from itertools import product, chain, combinations
from bisimulation_algorithms.utilities.kosaraju import kosaraju
from bisimulation_algorithms.utilities.rank_computation import (
    scc_finishing_time_list,
)


def add_edge(source: _Vertex, destination: _Vertex) -> _Edge:
    edge = _Edge(source, destination)
    if len(source.image) > 0:
        # there's already a _Count instance for the image of this Vertex,
        # therefore we HAVE to use it.
        edge.count = source.image[0].count
    else:
        edge.count = _Count(source)

    edge.count.value += 1

    source.add_to_image(edge)
    destination.add_to_counterimage(edge)

    return edge


def find_vertexes(
    partition: List[_Block], label1: int, label2: int
) -> Tuple[_Vertex, _Vertex]:
    source_vertex = None
    destination_vertex = None

    for block in partition:
        for node in block.vertexes:
            if node.label == label1:
                source_vertex = node
            if node.label == label2:
                destination_vertex = node

    if source_vertex is None:
        raise Exception(
            """It wasn't possible to determine the source vertex the new
            edge"""
        )
    if destination_vertex is None:
        raise Exception(
            """It wasn't possible to determine the destination vertex of the
            new edge"""
        )

    return (source_vertex, destination_vertex)


def check_old_blocks_relation(source_vertex, destination_vertex) -> bool:
    """If in the old RSCP [u] => [v], the addition of the new edge doesn't
    change the RSCP.

    Args:
        old_rscp (List[Tuple[int]]): The RSCP before the addition of the edge
            (each index of the outer-most list is linked to the rank of the
            blocks in the inner-most lists).
        new_edge (Tuple[_Vertex]): A tuple representing the new edge.

    Returns:
        bool: True if [u] => [v], False otherwise
    """

    # check if v is already in u's image
    for edge in source_vertex.image:
        if edge.destination.label == destination_vertex.label:
            return True

    # in fact the outer-most for-loop loops 2 times at most
    for vertex in source_vertex.qblock.vertexes:
        # we're interested in vertexes which aren't the source vertex of the
        # new edge.
        if vertex is not source_vertex:
            for edge in vertex.image:
                if edge.destination.qblock == destination_vertex.qblock:
                    return True
            # we visited the entire image of a single block (not u) of [u], and
            # it didn't contain an edge to [v], therefore we conclude (since
            # the old partition is stable if we don't consider the new edge)
            # that an edge from [u] to [v] can't exist
            return False
    # we didn't find an edge ([u] contains only u)
    return False


def check_new_scc(
    current_source: _Vertex,
    destination: _Vertex,
    finishing_time_list,
    min_rank: int = None,
    max_rank: int = None,
    visited_vertexes: List[_Vertex] = [],
    root_call=True,
) -> bool:
    # this is a consequence of the context where this function is used, keep
    # in mind when testing!
    if min_rank is None:
        min_rank = current_source.rank
    if max_rank is None:
        max_rank = destination.rank

    if root_call:
        current_source.visited = True
        current_source.qblock.visited = True
        visited_vertexes.append(current_source)

    flag_scc_found = False

    for edge in current_source.counterimage:
        # we reached the block [v], therefore this is a new SCC
        if edge.source == destination:
            flag_scc_found = True

        if (
            not edge.source.visited
            # and min_rank <= edge.source.rank
            # and edge.source.rank <= max_rank
        ):
            # we don't want to visit a vertex more than one time
            edge.source.visited = True
            visited_vertexes.append(edge.source)

            edge.source.qblock.visited = True

            # if at least one of the possible ramifications is True,
            # return True
            flag_scc_found = (
                check_new_scc(
                    edge.source,
                    destination,
                    finishing_time_list,
                    min_rank,
                    max_rank,
                    visited_vertexes,
                    root_call=False,
                )
                or flag_scc_found
            )

    finishing_time_list.append(current_source)

    # we have to clean the flag "visited" for each visited vertex
    if root_call:
        for vx in visited_vertexes:
            vx.visited = False

    return flag_scc_found


def both_blocks_go_or_dont_go_to_block(
    block1: _Block, block2: _Block, block_counterimage: List[_Vertex]
) -> bool:
    block1_goes = False
    block2_goes = False

    for vertex in block_counterimage:
        if vertex.qblock == block1:
            block1_goes = True
            # the situation changed: CHECK!
            if block2_goes:
                return True
        elif vertex.qblock == block2:
            block2_goes = True
            # the situation changed: CHECK!
            if block1_goes:
                return True

    return block1_goes == block2_goes


def exists_causal_splitter(
    block1: _Block, block2: _Block, check_visited
) -> bool:
    def plausible_causal_splitters(block, the_other_block):
        s = set()
        for v in block.vertexes:
            for edge in v.image:
                current_block = edge.destination.qblock
                # if check_visited is true, we only want to consider
                # qblock visited in the first DFS (flag visited is true)
                if not (check_visited and current_block.visited):
                    # causal splitter HAVE TO be blocks such that we KNOW they
                    # are in the new rscp of G' (the updated graph)
                    if (
                        current_block.rank < block.rank
                        or current_block == the_other_block
                    ):
                        s.add(id(edge.destination.qblock))
        return s

    block_image1 = plausible_causal_splitters(block1, block2)
    block_image2 = plausible_causal_splitters(block2, block1)

    return block_image1 != block_image2


def merge_condition(
    block1: _Block, block2: _Block, check_visited: bool = False
) -> bool:
    if (
        block1.initial_partition_block_id()
        != block2.initial_partition_block_id()
    ):
        return False
    elif block1 == block2:
        return False
    elif block1.rank != block2.rank:
        return False
    elif block1.deteached or block2.deteached:
        return False
    elif exists_causal_splitter(block1, block2, check_visited):
        return False
    else:
        return True


def recursive_merge(block1: _Block, block2: _Block):
    vertexes1 = list(block1.vertexes)
    vertexes2 = list(block2.vertexes)

    block1.merge(block2)

    # construct a list of couples of blocks which needs to be verified
    verified_couples = {}

    for vx1, vx2 in product(vertexes1, vertexes2):
        for edge1, edge2 in product(vx1.counterimage, vx2.counterimage):
            b1 = edge1.source.qblock
            b2 = edge2.source.qblock

            if (
                not (id(b1), id(b2)) in verified_couples
                or (id(b2), id(b1)) in verified_couples
            ):
                verified_couples[id(b1), id(b2)] = True
                if merge_condition(b1, b2):
                    recursive_merge(b1, b2)


def merge_phase(
    ublock: _Block,
    vblock: _Block,
):
    """If U1 => V && merge_condition(U,U1) then merge (U1,U). Then proceed
    recursively.

    Args:
        ublock (_Block):
        vblock (_Block):
    """
    for vertex in vblock.vertexes:
        for edge in vertex.counterimage:
            u1block = edge.source.qblock
            if merge_condition(ublock, u1block):
                recursive_merge(ublock, u1block)


def merge_step(vertex, X, visited_vertexes, cant_merge_dict):
    vertex.visited = True
    visited_vertexes.append(vertex)

    # try to merge this block
    if not vertex.qblock.tried_merge:
        initial_partition_block_id = vertex.qblock.initial_partition_block_id()
        # if there are blocks which can't be merged with each other in the
        # dict, we try to merge this with one of them
        if initial_partition_block_id in cant_merge_dict:
            merged = False
            # loop over blocks in the dict
            for qblock in cant_merge_dict[initial_partition_block_id]:
                if merge_condition(vertex.qblock, qblock, check_visited=True):
                    # it's preferable to deteach vertex.qblock instead of
                    # qblock in order to reduce the rubbish
                    recursive_merge(qblock, vertex.qblock)
                    merged = True
                    break
            if not merged:
                # if this blocks wasn't merged with anyone, add this block to
                # the dict
                cant_merge_dict[initial_partition_block_id].append(
                    vertex.qblock
                )
                # no merge, therefore we append the block to X
                X.append(vertex.qblock)
        else:
            # this is the first block for this initial label
            cant_merge_dict[initial_partition_block_id] = [vertex.qblock]
            # the block is the first of its initial_partition_block_id,
            # therefore we can put it into X
            X.append(vertex.qblock)

        vertex.qblock.tried_merge = True

    for edge in vertex.image:
        if not edge.destination.visited:
            merge_step(edge.destination, X, visited_vertexes, cant_merge_dict)


def preprocess_initial_partition(qblocks: List[_Block]):
    for block in qblocks:
        leafs = []
        non_leafs = []

        for vertex in block.vertexes:
            if len(vertex.image) == 0:
                leafs.append(vertex)
            else:
                non_leafs.append(vertex)

        # if at least one is not zero, this block needs to be splitted
        if len(leafs) * len(non_leafs) != 0:
            qblocks.append(block.fast_mitosis(leafs))


def merge_split_phase(qpartition, finishing_time_list):
    max_rank = float("-inf")
    for block in qpartition:
        max_rank = max(max_rank, block.rank)

    # a dict of lists of blocks (the key is the initial partition ID)
    # where each couple can't be merged
    cant_merge_dict = {}

    # keep track in order to remove the 'visited' flag
    visited_vertexes = []

    # a partition containing all the touched blocks
    X = []

    # visit G in order of decreasing finishing times of the first DFS
    for vertex in finishing_time_list:
        # a vertex may be reached more than one time
        if not vertex.visited:
            merge_step(vertex, X, visited_vertexes, cant_merge_dict)

    X = list(filter(lambda block: not block.deteached, X))

    # clear visited flag
    for vx in visited_vertexes:
        vx.visited = False

    # reset block.visited flag (was set by first DFS) and tried_merge
    for block in qpartition:
        block.visited = False
        block.tried_merge = False

    # ------------
    # Split phase
    # ------------

    # we need to scale in order to use PTA (and then scale back)
    scaled_to_nonscaled = []

    xblock = _XBlock()
    for block in X:
        # this is needed for PTA
        xblock.append_qblock(block)
        # set visited flag in order to compute the set (qpartition - X) easily
        block.visited = True

        for vx in block.vertexes:
            # mark as reachable by PTA
            vx.allow_visit = True
            # remember which qblock you were in
            vx.old_qblock_id = id(vx.qblock)

            # scale label in order to use PTA
            vx.scale_label(len(scaled_to_nonscaled))
            scaled_to_nonscaled.append(vx.label)

    # build the new qpartition, without the blocks in X (which may be split).
    # this is just the set qpartition - X
    new_qpartition = []
    for block in qpartition:
        if not (block.visited or block.deteached):
            new_qpartition.append(block)
        else:
            # now we can clean the flag, this block was already discarded
            block.visited = False

    for block in X:
        for vx in block.vertexes:
            vx.restrict_to_allowed_subraph()

    # apply PTA and append the blocks to the new partition
    preprocess_initial_partition(X)
    X2 = pta(X)
    new_qpartition.extend(X2)

    for block in X2:
        for vx in block.vertexes:
            # restore the original image/counterimage
            vx.back_to_original_graph()
            # clean allow_visit
            vx.allow_visit = False
            # restore original label
            vx.back_to_original_label()

    # keep track of the blocks which are the result of a split
    splitted_blocks = []
    for block in X2:
        for vx in block.vertexes:
            # check if splitted
            if not vx.qblock.visited and vx.old_qblock_id != id(vx.qblock):
                new_qpartition = ranked_split(
                    new_qpartition, vx.qblock, max_rank
                )
                splitted_blocks.append(vx.qblock)

                # this is used as a flag to prevent splitting twice
                vx.qblock.visited = True

    # clear old_qblock_id
    for block in new_qpartition:
        for vertex in block.vertexes:
            vertex.old_qblock_id = None

    # clean block.visited
    for block in splitted_blocks:
        block.visited = False

    return new_qpartition


def propagate_nwf(scc: _SCC, scc_finishing_time: List[_SCC]):
    if not scc.visited:
        scc.visited = True

        scc.compute_image()
        scc.compute_counterimage()

        if len(scc._image) == 0:
            if len(scc._vertexes) == 0:
                scc.mark_leaf()
            else:
                scc.mark_scc_leaf()
        else:
            mx = float("-inf")
            # at this point we can rely on the flag wf since the visit
            # occurs in the right order
            for image_scc in scc.image:
                if image_scc.wf is False:
                    scc._wf = False

                r = image_scc.rank
                mx = max(mx, r + 1 if image_scc.wf else r)
            scc._rank = mx

        # since we store rank and wf into SCCs, there's no need to propagate
        # the new rank to members of the SCC

        for sf in scc_finishing_time:
            if sf.label in scc._counterimage:
                propagate_nwf(sf, scc_finishing_time)


def propagate_wf(
    vertex: _Vertex,
    well_founded_topological: List[_Vertex],
    scc_finishing_time: List[_SCC],
):
    """Recursively visit the well-founded counterimage of the given vertex and
    update the ranks. The visit is in increasing order of rank. It can be shown
    easily that this is the only way to get correct results.

    Args:
        vertex (_Vertex): The updated vertex (source of the new edge). The rank
        must already be updated.
        well_founded_topological (List[_Vertex]): List of WF vertexes of the
        graph in topological order.
    """

    for vx in well_founded_topological:
        mx = vx.rank
        for edge in vx.image:
            if edge.destination.wf:
                mx = max(mx, edge.destination.rank + 1)
        vx.rank = mx

    # propagate the changes also to nwf nodes
    for vx in well_founded_topological:
        for edge in vx.counterimage:
            if not edge.source.wf:
                propagate_nwf(edge.source.scc, scc_finishing_time)


def build_well_founded_topological_list(old_rscp, source, max_rank):
    if source.rank == float("-inf"):
        source_position = 0
    else:
        source_position = source.rank + 1

    if max_rank == float("-inf"):
        buckets = [None]
    else:
        buckets = [None for _ in range(max_rank + 2 - source_position)]

    for block in old_rscp:
        if block.rank == float("-inf"):
            idx = 0
        elif block.rank >= source.rank:
            idx = block.rank + 1 - source_position
        else:
            # we ignore blocks of rank lower than the rank of the source
            continue

        if buckets[idx] is None:
            buckets[idx] = []

        for vx in block.vertexes:
            if vx.wf:
                buckets[idx].append(vx)

    wft = []
    for rank_list in buckets:
        if rank_list is not None:
            wft.extend(rank_list)
    return wft

    """ dict_by_rank = {}
    well_founded_topological = []
    for block in old_rscp:
        if block.rank in dict_by_rank:
            ls = dict_by_rank[block.rank]
        else:
            ls = []
            dict_by_rank[block.rank] = ls
        for vertex in block.vertexes:
            if vertex.wf:
                ls.append(vertex)
    for _, ls in dict_by_rank.items():
        well_founded_topological.extend(ls)
    return well_founded_topological """


def filter_deteached(blocks: List[_Block]) -> List[_Block]:
    return list(filter(lambda block: not block.deteached, blocks))


def update_rscp(
    old_rscp: List[_Block],
    new_edge: Tuple,
    vertexes: List[_Vertex],
):
    max_rank = max(map(lambda block: block.rank, old_rscp))

    if isinstance(new_edge[0], int) and isinstance(new_edge[1], int):
        source_vertex, destination_vertex = find_vertexes(old_rscp, *new_edge)
    elif isinstance(new_edge[0], _Vertex) and isinstance(new_edge[1], _Vertex):
        source_vertex, destination_vertex = new_edge
    else:
        raise ValueError("You must pass integers or Vertex instances!")

    well_founded_topological = build_well_founded_topological_list(
        old_rscp, vertexes[new_edge[0]], max_rank
    )

    sccs_dict = {}
    for vx in vertexes:
        sccs_dict[vx.scc.label] = vx.scc
    sccs = list(sccs_dict.values())

    for scc in sccs:
        scc.compute_image()

    scc_finishing_time = scc_finishing_time_list(sccs)

    # update immediately the wf flag
    if not destination_vertex.wf:
        source_vertex.wf = False

    # if the new edge connects two blocks A,B such that A => B before the edge
    # is added we don't need to do anything
    if check_old_blocks_relation(source_vertex, destination_vertex):
        return old_rscp
    else:
        # update the graph representation
        add_edge(source_vertex, destination_vertex)

        qpartition = ranked_split(
            old_rscp, destination_vertex.qblock, max_rank
        )

        # u isn't well founded, v is well founded
        if not source_vertex.wf and destination_vertex.wf:
            # if necessary, update the rank of u and propagate the changes
            if destination_vertex.rank + 1 > source_vertex.rank:
                source_vertex.rank = destination_vertex.rank + 1

                # source_vertex doesn't become nwf
                propagate_nwf(source_vertex.scc, scc_finishing_time)

            merge_phase(source_vertex.qblock, destination_vertex.qblock)
            return filter_deteached(qpartition)
        else:
            # in this case we don't need to update the rank
            if source_vertex.rank > destination_vertex.rank:
                merge_phase(source_vertex.qblock, destination_vertex.qblock)
                return filter_deteached(qpartition)
            else:
                # we want to save the finishing time list
                finishing_time_list = []

                # in this case u is part of the new SCC (which contains also
                # v), therefore it isn't well founded
                if check_new_scc(
                    source_vertex,
                    destination_vertex,
                    finishing_time_list,
                ):
                    sccs = kosaraju(source_vertex, return_sccs=True)
                    for scc in sccs:
                        scc.compute_image()
                        scc.compute_counterimage()

                    scc_finishing_time = scc_finishing_time_list(sccs)

                    propagate_nwf(source_vertex.scc, scc_finishing_time)
                    return merge_split_phase(qpartition, finishing_time_list)
                else:
                    if source_vertex.wf:
                        if destination_vertex.wf:
                            # we already know that u.rank <= v.rank
                            source_vertex.rank = destination_vertex.rank + 1
                            topological_sorted_wf = None
                            propagate_wf(
                                source_vertex,
                                well_founded_topological,
                                scc_finishing_time,
                            )
                        # u becomes non-well-founded
                        else:
                            if source_vertex.rank < destination_vertex.rank:
                                source_vertex.rank = destination_vertex.rank

                                propagate_nwf(
                                    source_vertex.scc, scc_finishing_time
                                )
                    else:
                        if source_vertex.rank < destination_vertex.rank:
                            source_vertex.rank = destination_vertex.rank

                            # we don't need to update the nwf list since
                            # source_vertex was already nwf

                            propagate_nwf(source_vertex, scc_finishing_time)

                    merge_phase(
                        source_vertex.qblock, destination_vertex.qblock
                    )
                    return filter_deteached(qpartition)
