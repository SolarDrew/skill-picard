from contextlib import contextmanager

__all__ = ['RoomMemory']


class RoomMemory:
    """
    A way of accessing opsdroid memory based on rooms.
    """
    def __init__(self, opsdroid):
        self.opsdroid = opsdroid

    @contextmanager
    def memory_in_room(self, room):
        ori_room = self.opsdroid.memory.databases[0].room
        self.opsdroid.memory.databases[0].room = room
        yield
        self.opsdroid.memory.databases[0].room = ori_room

    def __getitem__(self, item):
        return self.memory_in_room(item)
