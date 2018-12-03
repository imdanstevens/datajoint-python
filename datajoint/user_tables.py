"""
Hosts the table tiers, user relations should be derived from.
"""

import collections
from .table import Table
from .autopopulate import AutoPopulate
from .utils import from_camel_case, ClassProperty
from .errors import DataJointError

_base_regexp = r'[a-z][a-z0-9]*(_[a-z][a-z0-9]*)*'

# attributes that trigger instantiation of user classes
supported_class_attrs = {
    'key_source', 'describe', 'populate', 'progress', 'primary_key', 'proj', 'aggr', 'heading', 'fetch', 'fetch1',
    'insert', 'insert1', 'drop', 'drop_quick', 'delete', 'delete_quick',
    'get_df', 'df', 'get_head', 'head', 'get_tail', 'tail'}


class OrderedClass(type):
    """
    Class whose members are ordered
    See https://docs.python.org/3/reference/datamodel.html#metaclass-example

    Note:  Since Python 3.6, _ordered_class_members will no longer be necessary (PEP 520)
    https://www.python.org/dev/peps/pep-0520/
    """
    @classmethod
    def __prepare__(metacls, name, bases, **kwds):
        return collections.OrderedDict()

    def __new__(cls, name, bases, namespace, **kwds):
        result = type.__new__(cls, name, bases, dict(namespace))
        result._ordered_class_members = list(namespace)
        return result

    def __setattr__(cls, name, value):
        if hasattr(cls, '_ordered_class_members'):
            cls._ordered_class_members.append(name)
        super().__setattr__(name, value)

    def __getattribute__(cls, name):
        # trigger instantiation for supported class attrs
        return (cls().__getattribute__(name) if name in supported_class_attrs
                else super().__getattribute__(name))

    def __and__(cls, arg):
        return cls() & arg

    def __sub__(cls, arg):
        return cls() - arg

    def __mul__(cls, arg):
        return cls() * arg

    def __add__(cls, arg):
        return cls() + arg

    def __iter__(cls):
        return iter(cls())


class UserTable(Table, metaclass=OrderedClass):
    """
    A subclass of UserTable is a dedicated class interfacing a base relation.
    UserTable is initialized by the decorator generated by schema().
    """
    _connection = None
    _heading = None
    tier_regexp = None
    _prefix = None

    @property
    def definition(self):
        """
        :return: a string containing the table definition using the DataJoint DDL.
        """
        raise NotImplementedError('Subclasses of Table must implement the property "definition"')

    @ClassProperty
    def connection(cls):
        return cls._connection

    @ClassProperty
    def table_name(cls):
        """
        :returns: the table name of the table formatted for mysql.
        """
        if cls._prefix is None:
            raise AttributeError('Class prefix is not defined!')
        return cls._prefix + from_camel_case(cls.__name__)

    @ClassProperty
    def full_table_name(cls):
        if cls not in {Manual, Imported, Lookup, Computed, Part}:
            if cls.database is None:
                raise DataJointError('Class %s is not properly declared (schema decorator not applied?)' % cls.__name__)
            return r"`{0:s}`.`{1:s}`".format(cls.database, cls.table_name)


class Manual(UserTable):
    """
    Inherit from this class if the table's values are entered manually.
    """
    _prefix = r''
    tier_regexp = r'(?P<manual>' + _prefix + _base_regexp + ')'


class Lookup(UserTable):
    """
    Inherit from this class if the table's values are for lookup. This is
    currently equivalent to defining the table as Manual and serves semantic
    purposes only.
    """
    _prefix = '#'
    tier_regexp = r'(?P<lookup>' + _prefix + _base_regexp.replace('TIER', 'lookup') + ')'


class Imported(UserTable, AutoPopulate):
    """
    Inherit from this class if the table's values are imported from external data sources.
    The inherited class must at least provide the function `_make_tuples`.
    """
    _prefix = '_'
    tier_regexp = r'(?P<imported>' + _prefix + _base_regexp + ')'


class Computed(UserTable, AutoPopulate):
    """
    Inherit from this class if the table's values are computed from other relations in the schema.
    The inherited class must at least provide the function `_make_tuples`.
    """
    _prefix = '__'
    tier_regexp = r'(?P<computed>' + _prefix + _base_regexp + ')'


class Part(UserTable):
    """
    Inherit from this class if the table's values are details of an entry in another relation
    and if this table is populated by this relation. For example, the entries inheriting from
    dj.Part could be single entries of a matrix, while the parent table refers to the entire matrix.
    Part relations are implemented as classes inside classes.
    """

    _connection = None
    _heading = None
    _master = None

    tier_regexp = r'(?P<master>' + '|'.join(
        [c.tier_regexp for c in (Manual, Lookup, Imported, Computed)]
    ) + r'){1,1}' + '__' + r'(?P<part>' + _base_regexp + ')'

    @ClassProperty
    def connection(cls):
        return cls._connection

    @ClassProperty
    def full_table_name(cls):
        return None if cls.database is None or cls.table_name is None else r"`{0:s}`.`{1:s}`".format(
            cls.database, cls.table_name)

    @ClassProperty
    def master(cls):
        return cls._master

    @ClassProperty
    def table_name(cls):
        return None if cls.master is None else cls.master.table_name + '__' + from_camel_case(cls.__name__)

    def delete(self, force=False):
        """
        unless force is True, prohibits direct deletes from parts.
        """
        if force:
            super().delete()
        else:
            raise DataJointError('Cannot delete from a Part directly.  Delete from master instead')

    def drop(self, force=False):
        """
        unless force is True, prohibits direct deletes from parts.
        """
        if force:
            super().drop()
        else:
            raise DataJointError('Cannot drop a Part directly.  Delete from master instead')
