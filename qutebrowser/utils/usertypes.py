# Copyright 2014 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Custom useful datatypes.

Module attributes:
    _UNSET: Used as default argument in the constructor so default can be None.
"""

import operator
import collections.abc

from PyQt5.QtCore import pyqtSignal, QObject

from qutebrowser.utils.log import misc as logger


_UNSET = object()


def enum(*items, start=0):
    """Factory for simple enumerations.

    We really don't need more complex things here, so we don't use python3.4's
    enum, because we'd have to backport things to 3.3 and maybe even 3.2.

    Based on: http://stackoverflow.com/a/1695250/2085149

    Args:
        *items: Items to be sequentally enumerated.
        start: The number to use for the first value.
    """
    numbers = range(start, len(items) + start)
    enums = dict(zip(items, numbers))
    return EnumBase('Enum', (), enums)


class EnumBase(type):

    """Metaclass for enums to provide __getitem__ for reverse mapping."""

    def __init__(cls, name, base, fields):
        super().__init__(name, base, fields)
        cls._mapping = dict((v, k) for k, v in fields.items())

    def __getitem__(cls, key):
        return cls._mapping[key]


class NeighborList(collections.abc.Sequence):

    """A list of items which saves it current position.

    Class attributes:
        Modes: Different modes, see constructor documentation.

    Attributes:
        idx: The current position in the list.
        fuzzyval: The value which is currently set but not in the list.
        _items: A list of all items, accessed through item property.
        _mode: The current mode.
    """

    Modes = enum('block', 'wrap', 'exception')

    def __init__(self, items=None, default=_UNSET, mode=Modes.exception):
        """Constructor.

        Args:
            items: The list of items to iterate in.
            _default: The initially selected value.
            _mode: Behaviour when the first/last item is reached.
                   Modes.block: Stay on the selected item
                   Modes.wrap: Wrap around to the other end
                   Modes.exception: Raise an IndexError.
        """
        if items is None:
            self._items = []
        else:
            self._items = list(items)
        self._default = default
        if default is not _UNSET:
            self.idx = self._items.index(default)
        else:
            self.idx = None
        self._mode = mode
        self.fuzzyval = None

    def __getitem__(self, key):
        return self._items[key]

    def __len__(self):
        return len(self._items)

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self._items)

    def _snap_in(self, offset):
        """Set the current item to the closest item to self.fuzzyval.

        Args:
            offset: negative to get the next smaller item, positive for the
                    next bigger one.

        Return:
            True if the value snapped in (changed),
            False when the value already was in the list.
        """
        op = operator.le if offset < 0 else operator.ge
        items = [(idx, e) for (idx, e) in enumerate(self._items)
                 if op(e, self.fuzzyval)]
        close_item = min(items, key=lambda tpl: abs(self.fuzzyval - tpl[1]))
        self.idx = close_item[0]
        return self.fuzzyval not in self._items

    def _get_new_item(self, offset):
        """Logic for getitem to get the item at offset.

        Args:
            offset: The offset of the current item, relative to the last one.

        Return:
            The new item.

        Raise:
            IndexError if the border of the list is reached and mode is
                       exception.
        """
        try:
            if self.idx + offset >= 0:
                new = self._items[self.idx + offset]
            else:
                raise IndexError
        except IndexError:
            if self._mode == self.Modes.block:
                new = self.curitem()
            elif self._mode == self.Modes.wrap:
                self.idx += offset
                self.idx %= len(self.items)
                new = self.curitem()
            elif self._mode == self.Modes.exception:
                raise
        else:
            self.idx += offset
        return new

    @property
    def items(self):
        """Getter for items, which should not be set."""
        return self._items

    def getitem(self, offset):
        """Get the item with a relative position.

        Args:
            offset: The offset of the current item, relative to the last one.

        Return:
            The new item.

        Raise:
            IndexError if the border of the list is reached and mode is
                       exception.
        """
        logger.debug("{} items, idx {}, offset {}".format(len(self._items),
                                                          self.idx, offset))
        if not self._items:
            raise IndexError("No items found!")
        if self.fuzzyval is not None:
            # Value has been set to something not in the list, so we snap in to
            # the closest value in the right direction and count this as one
            # step towards offset.
            snapped = self._snap_in(offset)
            if snapped and offset > 0:
                offset -= 1
            elif snapped:
                offset += 1
            self.fuzzyval = None
        return self._get_new_item(offset)

    def curitem(self):
        """Get the current item in the list."""
        if self.idx is not None:
            return self._items[self.idx]
        else:
            raise IndexError("No current item!")

    def nextitem(self):
        """Get the next item in the list."""
        return self.getitem(1)

    def previtem(self):
        """Get the previous item in the list."""
        return self.getitem(-1)

    def firstitem(self):
        """Get the first item in the list."""
        if not self._items:
            raise IndexError("No items found!")
        self.idx = 0
        return self.curitem()

    def lastitem(self):
        """Get the last item in the list."""
        if not self._items:
            raise IndexError("No items found!")
        self.idx = len(self._items) - 1
        return self.curitem()

    def reset(self):
        """Reset the position to the default."""
        if self._default is _UNSET:
            raise ValueError("No default set!")
        else:
            self.idx = self._items.index(self._default)
            return self.curitem()


# The mode of a Question.
PromptMode = enum('yesno', 'text', 'user_pwd', 'alert')


class Question(QObject):

    """A question asked to the user, e.g. via the status bar.

    Attributes:
        mode: A PromptMode enum member.
              yesno: A question which can be answered with yes/no.
              text: A question which requires a free text answer.
              user_pwd: A question for an username and password.
        default: The default value.
                 For yesno, None (no default), True or False.
                 For text, a default text as string.
                 For user_pwd, a default username as string.
        text: The prompt text to display to the user.
        user: The value the user entered as username.
        answer: The value the user entered (as password for user_pwd).

    Signals:
        answered: Emitted when the question has been answered by the user.
                  This is emitted from qutebrowser.widgets.statusbar._prompt so
                  it can be emitted after the mode is left.
        answered_yes: Convienience signal emitted when a yesno question was
                      answered with yes.
        answered_no: Convienience signal emitted when a yesno question was
                     answered with no.
    """

    answered = pyqtSignal()
    answered_yes = pyqtSignal()
    answered_no = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = None
        self.default = None
        self.text = None
        self.user = None
        self.answer = None
