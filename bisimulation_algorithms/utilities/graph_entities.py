from llist import dllist, dllistnode
from typing import Iterable


def compute_initial_partition_block_id(vertex_labels: Iterable[int]):
    id = 0
    for label in vertex_labels:
        id += pow(2, label)
    return id


class _Vertex:
    """BisPy representation of a vertex in a graph. Contains several data
    structures which provide O(1) access to the adjacency list of the vertex,
    as well as attributes to store temporary information used or shared among
    different parts of the algorithm (make sure to reset them when they aren't
    needed anymore).

    :param int label: A unique (in the graph) integer ID which identifies this
        vertex. `label`s must be an interval (no holes) starting from zero,
        otherwise the algorithm may not work properly.
    """

    def __init__(self, label):
        """Constructor method
        """
        self._label = label
        self._qblock = None

        # the dllistobject which refers to this vertex inside the dllist inside
        # the QBlock which contains this vertex
        self._dllistnode = None

        # a property shared by many algorithms, reset it to False after usage
        self.visited = False

        # a list of `_Edge` instances from `self` to the `_Vertex` instances in
        # the image of this `_Vertex`.
        self.image = []
        # a list of `_Edge` instances from `self` to the `_Vertex` instances in
        # the counterimage of this `_Vertex`.
        self.counterimage = []

        self.aux_count = None
        self.in_second_splitter = False

        self._original_label = label

        self.initial_partition_block_id = None

        self.allow_visit = False
        self.old_qblock_id = None

        self._scc = None

    @property
    def label(self):
        """The current label assigned to this :class:`_Vertex` instance. May
        change if a method like :func:`scale_label` is called."""
        return self._label

    @property
    def original_label(self):
        """The original label assigned to this :class:`_Vertex` instance. Is a
        constant value."""
        return self._original_label

    @property
    def qblock(self):
        """The :class:`_QBlock` instance that this :class:`_Vertex` belongs to
        at the moment."""
        return self._qblock

    @property
    def scc(self):
        return self._scc

    @scc.setter
    def scc(self, value):
        self._scc = value

    def scale_label(self, scaled_label: int):
        self._label = scaled_label

    def back_to_original_label(self):
        self._label = self.original_label

    # creates a subgraph which contains only vertexes of the
    # same rank of this vertex.
    def restrict_to_subgraph(self):
        # this will be called just before calling PTA, therefore set the _Count
        # instance for each _Edge

        img = self.image
        self.image = []

        count = _Count(self)

        for edge in img:
            if edge.destination.rank == self.rank:
                self.add_to_image(edge)

                # set the count for this _Edge, and increment the counter
                edge.count = count
                count.value += 1

        counterimg = self.counterimage
        self.counterimage = []

        for edge in counterimg:
            if edge.source.rank == self.rank:
                self.add_to_counterimage(edge)

    def restrict_to_allowed_subraph(self):
        self._original_img = self.image
        self.image = []

        self._original_count = None

        count = _Count(self)

        for edge in self._original_img:
            if edge.destination.allow_visit:
                self.add_to_image(edge)

                if self._original_count is None:
                    self._original_count = edge.count

                # set the count for this _Edge, and increment the counter
                edge.count = count
                count.value += 1

        self._original_counterimg = self.counterimage
        self.counterimage = []

        for edge in self._original_counterimg:
            if edge.source.allow_visit:
                self.add_to_counterimage(edge)

    def back_to_original_graph(self):
        self.image = self._original_img
        self.counterimage = self._original_counterimg

        for edge in self.image:
            edge.count = self._original_count

        self._original_count = None
        self._original_counterimg = None
        self._original_img = None

    def add_to_counterimage(self, edge):
        self.counterimage.append(edge)

    def add_to_image(self, edge):
        self.image.append(edge)

    def visit(self):
        self.visited = True

    def release(self):
        self.visited = False

    def added_to_second_splitter(self):
        self.in_second_splitter = True

    def clear_second_splitter_flag(self):
        self.in_second_splitter = False

    @property
    def rank(self):
        return self.scc.rank

    @rank.setter
    def rank(self, value):
        self.scc._rank = value

    @property
    def wf(self):
        return self.scc.wf

    @wf.setter
    def wf(self, value):
        self.scc._wf = value

    def __repr__(self):
        return "V{}".format(self.label)


class _Edge:
    """Represents an edge between two _Vertex instances.

    Attributes:
        source                  The source _Vertex of this edge.
        destination             The destination _Vertex of this edge.
        count                   A _Count instance which holds |E({source})
            cap S|, where S is the block of X destination belongs to.
    """

    def __init__(self, source: _Vertex, destination: _Vertex):
        self.source = source
        self.destination = destination

        # holds the value count(source,S) = |E({source}) \cap S|
        self.count = None

    # this is only used for testing purposes
    def __hash__(self):
        return hash("{}-{}".format(self.source.label, self.destination.label))

    def __eq__(self, other):
        return (
            isinstance(other, _Edge)
            and self.source == other.source
            and self.destination == other.destination
        )

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "<{},{}>".format(self.source, self.destination)


class _QBlock:
    def __init__(self, vertexes, xblock):
        self.vertexes = dllist([])

        for vertex in vertexes:
            self.append_vertex(vertex)

        self.size = self.vertexes.size
        self.split_helper_block = None
        self.dllistnode = None
        self.visited = False

        if xblock is not None:
            xblock.append_qblock(self)

        self.deteached = False
        self.tried_merge = False

    # this doesn't check if the vertex is a duplicate.
    # make sure that vertex is a proper _Vertex, not a dllistnode
    def append_vertex(self, vertex: _Vertex):
        vertex._dllistnode = self.vertexes.append(vertex)
        self.size = self.vertexes.size
        vertex._qblock = self

    # throws an error if the vertex isn't inside this qblock
    def remove_vertex(self, vertex: _Vertex):
        self.vertexes.remove(vertex._dllistnode)
        self.size = self.vertexes.size
        vertex._qblock = None

    def initialize_split_helper_block(self):
        self.split_helper_block = _QBlock([], self.xblock)

    def reset_helper_block(self):
        self.split_helper_block = None

    @property
    def rank(self) -> int:
        if self.vertexes.first is not None:
            return self.vertexes.first.value.rank
        else:
            return None

    @property
    def xblock(self):
        if hasattr(self, "_xblock"):
            return self._xblock
        else:
            return None

    @xblock.setter
    def xblock(self, value):
        self._xblock = value

    def initialize_split_helper_block(self):
        self.split_helper_block = _QBlock([], self.xblock)

    def initial_partition_block_id(self):
        if self.vertexes.size > 0:
            return self.vertexes.first.value.initial_partition_block_id
        else:
            return None

    def merge(self, block2):
        for vertex in block2.vertexes:
            self.append_vertex(vertex)
        block2.deteached = True

    def __repr__(self):
        return "Q({})".format(
            ",".join([str(vertex) for vertex in self.vertexes])
        ) + ("DET" if self.deteached else "")

    def fast_mitosis(self, extract_vertexes):
        new_block = _QBlock([], self.xblock)
        for vertex in extract_vertexes:
            self.remove_vertex(vertex)
            new_block.append_vertex(vertex)
        return new_block

    # only for testing purposes
    def _mitosis(self, vertexes1, vertexes2):
        new_block = _QBlock([], self.xblock)

        for to_remove in vertexes2:
            for vertex in self.vertexes:
                if to_remove == vertex.label:
                    self.remove_vertex(vertex)
                    new_block.append_vertex(vertex)

        return new_block


class _XBlock:
    """A block of X in the Paige-Tarjan algorithm.

    Attributes:
        qblocks                     A dllist which contains the
            blocks Q1,...,Qn such that the union of Q1,...,Qn is equal to self.
    """

    def __init__(self):
        self.qblocks = dllist([])

    def size(self):
        return self.qblocks.size

    def append_qblock(self, qblock: _QBlock):
        qblock.dllistnode = self.qblocks.append(qblock)
        qblock.xblock = self
        return self

    def remove_qblock(self, qblock: _QBlock):
        self.qblocks.remove(qblock.dllistnode)
        qblock.xblock = None

    def __repr__(self):
        return "X[{}]".format(",".join(str(qblock) for qblock in self.qblocks))


# holds the value of count(vertex,_XBlock) = |_XBlock \cap E({vertex})|
class _Count:
    """A class whcih represents a value. This is used to hold, share, and
    propagate changes in O(1) between all the interested entities (vertexes in
    the case of vertex.aux_count, edges in the case of edge.count).

    Attributes:
        vertex                    The vertex this instance is associated to,
            namely the x such that self = count(x,A).
        xblock                    The XBlock this isntance is associated to,
            namely the S such that self = count(x,S).
        value                     The current value of this instance (shared
            between all the "users" of the reference).
    """

    def __init__(self, vertex: _Vertex):
        self.vertex = vertex
        self.value = 0

    def __repr__(self):
        return "C{}:{}".format(self.vertex, self.value)


class _SCC:
    def __init__(self, label: int):
        self._label = label
        self._rank = float("-inf")

        self._image = {}
        self._counterimage = {}

        self._vertexes = set()

        self.visited = False

    def add_vertex(self, vertex: _Vertex):
        self._vertexes.add(vertex)
        vertex.scc = self

    @property
    def wf(self):
        if not hasattr(self, "_wf"):
            if len(self._vertexes) > 1:
                self._wf = False
            else:
                self._wf = True
                for scc in self.image:
                    if not scc.wf:
                        self._wf = False
                        break
        return self._wf

    @property
    def rank(self):
        return self._rank

    def mark_leaf(self):
        self._rank = 0

    def mark_scc_leaf(self):
        self._rank = float("-inf")

    def compute_image(self):
        self._image.clear()
        for vx in self._vertexes:
            for edge in vx.image:
                # edge towards self
                if edge.destination.scc == self:
                    self._wf = False
                else:
                    # NO! there's no guarantee that the visit occurs
                    # in the right order. we can't rely on the .wf
                    # field of successors, since it may not be the truth
                    # if not edge.destination.wf:
                    #    self._wf = False
                    self._image[
                        edge.destination.scc.label
                    ] = edge.destination.scc

    def compute_counterimage(self):
        self._counterimage.clear()
        for vx in self._vertexes:
            for edge in vx.counterimage:
                # edge towards self, don't include
                if edge.source.scc == self:
                    continue
                else:
                    self._counterimage[edge.source.scc.label] = edge.source.scc

    @property
    def label(self):
        return self._label

    @property
    def image(self):
        return self._image.values()

    @property
    def counterimage(self):
        return self._counterimage.values()

    def destroy(self):
        self._vertexes.clear()
        self._image.clear()
        self._counterimage.clear()

    def join(self, other):
        for vertex in other._vertexes:
            self.add_vertex(vertex)
        self._rank = None
        self._wf = False
        other.destroy()

    def __repr__(self):
        return "SCC({})".format(
            ",".join([str(vertex) for vertex in self._vertexes])
        )
