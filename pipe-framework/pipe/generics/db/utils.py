import copy
import typing as t

from orator import DatabaseManager
from typeguard import typechecked


@typechecked
class DatabaseBaseMixin:
    """
    Generic mixin for all Steps related to Database
    """
    connection_config: t.Optional[t.Dict[str, str]] = None
    data_field: str = 'data'
    pk_field: str = 'id'
    one_shot: bool = True
    table_name: t.Optional[str] = None
    __db = None
    query = None

    def __init__(self, table_name: t.Optional[str] = None, data_field: t.Optional[str] = None,
                 pk_field: str = 'id',
                 where: t.Optional[tuple] = None, join: t.Optional[tuple] = None,
                 select: t.Optional[tuple] = None,
                 one_shot: bool = True):

        self.data_field = data_field
        self.table_name = table_name
        self.pk_field = pk_field
        self.one_shot = one_shot

        self.where_clause = where
        self.join_clause = join
        self.select_clause = select

    def set_table(self, table_name: str):
        """
        :param table_name:
        :return: Orator Query builder
        """
        self.query = self.__db.table(table_name)

        return self.query

    def set_select(self, select: t.Optional[tuple] = None):
        """
        Sets columns for selecting. See Orator docs for detailed info
        :param select:
        :return:
        """
        if select is not None:
            return self.query.select(*select)

    def set_where(self, where: t.Optional[tuple] = None):
        """
        Sets where clause. See Orator docs for detailed info

        :param where:
        :return: Orator Query builder
        """
        if where is not None:
            return self.query.where(*where)

    def set_join(self, join: t.Optional[tuple] = None):
        """
        Sets join clause. See Orator docs for detailed info.

        :param join:
        :return: Orator Query builder
        """
        if join is not None:
            return self.query.join(*join)

    def create_connection(self) -> t.NoReturn:
        """
        Creates connection to database if it is None
        """
        if self.__db is None:
            self.__db = DatabaseManager(self.connection_config)

    def clear_connection(self):
        """
        Clears connection
        """
        self.__db.disconnect()
        self.__db = None


@typechecked
class CreateUpdateMixin:
    def insert(self, data: t.Dict):
        """
        Inserts data into a table

        :param data:
        :return: id of inseted string
        """
        self.create_connection()
        return self.set_table(self.table_name).insert_get_id(data)

    def update(self, data: t.Dict):
        """
        Updates data in the table

        :param data:
        :return: query instance
        """
        self.create_connection()
        pk = copy.deepcopy(data).pop(self.pk_field)

        self.set_table(self.table_name)
        self.set_where(self.where_clause)
        self.set_join(self.join_clause)

        return self.query.update(data)


@typechecked
class ReadMixin:
    """
    Small mixin which implements simplest 'select' operation for extracting.
    If this method do not fullfill all your requirements, you have to create your own extractor.
    """

    def select(self, pk: t.Optional[int] = None) -> t.Union[t.Mapping, list]:
        """
        Returns list of the objects from database or just one object, if 'pk' param is presented

        :param pk:
        """
        self.create_connection()
        self.set_table(self.table_name)

        if pk is not None:
            self.set_where((self.pk_field, '=', pk, 'and'))

        self.set_select(self.select_clause)
        self.set_join(self.join_clause)
        self.set_where(self.where_clause)

        if pk is not None:
            return self.query.first()
        else:
            return list(self.query.get())


@typechecked
class DeleteMixin:
    def delete(self, pk: t.Optional[int]):
        """
        Deletes object by a 'pk' or by a where clause if presented

        :param pk:
        """
        self.create_connection()

        self.set_table(self.table_name)

        if len(self.where_clause) > 0:
            self.set_where(self.where_clause)
        else:
            self.set_where((self.pk_field, '=', pk, 'and'))

        self.set_join(self.join_clause)

        return self.query.delete()