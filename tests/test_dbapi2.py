from __future__ import unicode_literals, absolute_import

from comdb2.dbapi2 import *
from comdb2 import cdb2
import pytest
import datetime
import pytz
import functools

COLUMN_LIST = ("short_col u_short_col int_col u_int_col longlong_col"
               " float_col double_col byte_col byte_array_col"
               " cstring_col pstring_col blob_col datetime_col vutf8_col"
               ).split()

COLUMN_TYPE = (NUMBER, NUMBER, NUMBER, NUMBER, NUMBER,
               NUMBER, NUMBER, BINARY, BINARY,
               STRING, STRING, BINARY, DATETIME, STRING)


@pytest.fixture(autouse=True)
def delete_all_rows():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    while True:
        cursor.execute("delete from all_datatypes limit 100")
        conn.commit()
        if cursor.rowcount != 100:
            break
    while True:
        cursor.execute("delete from simple limit 100")
        conn.commit()
        if cursor.rowcount != 100:
            break
    while True:
        cursor.execute("delete from strings limit 100")
        conn.commit()
        if cursor.rowcount != 100:
            break
    conn.close()


def test_invalid_cluster():
    with pytest.raises(OperationalError):
        conn = connect('mattdb', 'foo')


def test_invalid_dbname():
    with pytest.raises(OperationalError):
        conn = connect('', 'dev')


def test_closing_unused_connection():
    conn = connect('mattdb', 'dev')
    conn.close()


def test_garbage_collecting_unused_connection():
    conn = connect('mattdb', 'dev')
    del conn


def test_commit_on_unused_connection():
    conn = connect('mattdb', 'dev')
    conn.commit()


def test_rollback_on_unused_connection():
    conn = connect('mattdb', 'dev')
    conn.rollback()


def test_inserts():
    # Without params
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("insert into simple(key, val) values(1, 2)")
    cursor.connection.commit()
    assert cursor.rowcount == 1

    cursor.execute("select key, val from simple order by key")
    assert cursor.fetchall() == [[1,2]]

    # With params
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("insert into simple(key, val) values(%(k)s, %(v)s)", dict(k=3, v=4))
    conn.commit()
    assert cursor.rowcount == 1

    cursor.execute("select key, val from simple order by key")
    assert cursor.fetchall() == [[1,2],[3,4]]


def test_rollback():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("insert into simple(key, val) values(1, 2)")
    conn.rollback()

    cursor.execute("select key, val from simple order by key")
    assert cursor.fetchall() == []


def test_commit_failures():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.executemany("insert into simple(key, val) values(%(key)s, %(val)s)",
                       [ dict(key=1, val=2), dict(key=3, val=None) ])
    with pytest.raises(IntegrityError):
        conn.commit()
        assert cursor.rowcount == 0

    cursor.execute("select * from simple")
    assert cursor.fetchall() == []


def test_implicitly_closing_old_cursor_when_opening_a_new_one():
    conn = connect('mattdb', 'dev')
    cursor1 = conn.cursor()
    cursor2 = conn.cursor()
    with pytest.raises(InterfaceError):
        assert cursor1.rowcount == -1
    assert cursor2.rowcount == -1


def test_commit_after_cursor_close():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("insert into simple(key, val) values(1, 2)")
    conn.commit()
    cursor.execute("insert into simple(key, val) values(3, 4)")
    cursor.close()
    conn.commit()

    cursor = conn.cursor()
    cursor.execute("select key, val from simple order by key")
    assert cursor.fetchall() == [[1,2],[3,4]]


def test_implicit_rollback_on_connection_close():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("insert into simple(key, val) values(1, 2)")
    conn.commit()
    cursor.execute("insert into simple(key, val) values(3, 4)")

    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    rows = list(cursor.execute("select key, val from simple order by key"))
    assert rows == [[1,2]]


def test_reading_and_writing_datetimes():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    ts_obj = Timestamp(2015, 1, 2, 3, 4, 5, 123000, pytz.UTC)
    ts_str_in = '2015-01-02T03:04:05.12345'
    ts_str_out = '2015-01-02T030405.123 UTC'

    cursor.execute("select cast(%(x)s as date)", dict(x=ts_str_in))
    assert cursor.fetchall() == [[ts_obj]]

    cursor.execute("select %(x)s || ''", dict(x=ts_obj))
    assert cursor.fetchall() == [[ts_str_out]]


def test_inserting_one_row_with_all_datatypes_without_parameters():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("insert into all_datatypes(" + ', '.join(COLUMN_LIST) + ")"
                   " values(1, 2, 3, 4, 5, .5, .25, x'01', x'0102030405',"
                          " 'hello', 'goodbye', x'01020304050607',"
                          " cast(1234567890.2345 as datetime), 'hello world')")
    conn.commit()
    assert cursor.rowcount == 1

    cursor.execute("select " + ', '.join(COLUMN_LIST) + " from all_datatypes")

    for i in range(len(COLUMN_LIST)):
        assert cursor.description[i][0] == COLUMN_LIST[i]
        for type_object in (STRING, BINARY, NUMBER, DATETIME):
            assert ((type_object == cursor.description[i][1])
                    == (type_object == COLUMN_TYPE[i]))
        assert cursor.description[i][2:] == (None, None, None, None, None)

    row = cursor.fetchone()
    assert row == [1, 2, 3, 4, 5, 0.5, 0.25,
                   Binary('\x01'), Binary('\x01\x02\x03\x04\x05'),
                   'hello', 'goodbye',
                   Binary('\x01\x02\x03\x04\x05\x06\x07'),
                   Datetime(2009, 2, 13, 18, 31, 30, 234000,
                            pytz.timezone("America/New_York")),
                   "hello world"]
    assert cursor.fetchone() == None


def test_all_datatypes_as_parameters():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    params = (
        ("short_col", 32767),
        ("u_short_col", 65535),
        ("int_col", 2147483647),
        ("u_int_col", 4294967295),
        ("longlong_col", 9223372036854775807),
        ("float_col", .125),
        ("double_col", 2.**65),
        ("byte_col", Binary(b'\x00')),
        ("byte_array_col", Binary(b'\x02\x01\x00\x01\x02')),
        ("cstring_col", 'HELLO'),
        ("pstring_col", 'GOODBYE'),
        ("blob_col", Binary('')),
        ("datetime_col", Datetime(2009, 2, 13, 18, 31, 30, 234000,
                                   pytz.timezone("America/New_York"))),
        ("vutf8_col", "foo"*50)
    )
    cursor.execute("insert into all_datatypes(" + ', '.join(COLUMN_LIST) + ")"
                   " values(%(short_col)s, %(u_short_col)s, %(int_col)s,"
                   " %(u_int_col)s, %(longlong_col)s, %(float_col)s,"
                   " %(double_col)s, %(byte_col)s, %(byte_array_col)s,"
                   " %(cstring_col)s, %(pstring_col)s, %(blob_col)s,"
                   " %(datetime_col)s, %(vutf8_col)s)", dict(params))

    conn.commit()

    cursor.execute("select * from all_datatypes")
    row = cursor.fetchone()
    assert row == list(v for k,v in params)
    assert cursor.fetchone() == None


def test_naive_datetime_as_parameter():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    params = (
        ("short_col", 32767),
        ("u_short_col", 65535),
        ("int_col", 2147483647),
        ("u_int_col", 4294967295),
        ("longlong_col", 9223372036854775807),
        ("float_col", .125),
        ("double_col", 2.**65),
        ("byte_col", Binary(b'\x00')),
        ("byte_array_col", Binary(b'\x02\x01\x00\x01\x02')),
        ("cstring_col", 'HELLO'),
        ("pstring_col", 'GOODBYE'),
        ("blob_col", Binary('')),
        ("datetime_col", Datetime(2009, 2, 13, 18, 31, 30, 234000)),
        ("vutf8_col", "foo"*50)
    )

    cursor.execute("insert into all_datatypes(" + ', '.join(COLUMN_LIST) + ")"
                   " values(%(short_col)s, %(u_short_col)s, %(int_col)s,"
                   " %(u_int_col)s, %(longlong_col)s, %(float_col)s,"
                   " %(double_col)s, %(byte_col)s, %(byte_array_col)s,"
                   " %(cstring_col)s, %(pstring_col)s, %(blob_col)s,"
                   " %(datetime_col)s, %(vutf8_col)s)", dict(params))

    cursor.connection.commit()
    cursor.execute("select datetime_col from all_datatypes")
    row = cursor.fetchone()
    assert row == [Datetime(2009, 2, 13, 18, 31, 30, 234000, pytz.UTC)]
    assert cursor.fetchone() is None


def test_rounding_datetime_to_nearest_millisecond():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()

    curr_microsecond = Datetime(2016, 2, 28, 23, 59, 59, 999499, pytz.UTC)
    prev_millisecond = Datetime(2016, 2, 28, 23, 59, 59, 999000, pytz.UTC)
    next_millisecond = Datetime(2016, 2, 29, 0, 0, 0, 0, pytz.UTC)

    cursor.execute("select @date", {'date': curr_microsecond})
    assert cursor.fetchall() == [[prev_millisecond]]

    curr_microsecond += datetime.timedelta(microseconds=1)
    cursor.execute("select @date", {'date': curr_microsecond})
    assert cursor.fetchall() == [[next_millisecond]]


def test_cursor_description():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    assert cursor.description is None

    cursor.execute("select 1")
    assert cursor.description == (("1", NUMBER, None, None, None, None, None),)

    cursor.execute("select 1 where 1=0")
    assert len(cursor.description) == 1
    assert cursor.description[0][0] == "1"

    cursor.execute("select '1' as foo, cast(1 as datetime) bar")
    assert cursor.description == (
        ("foo", STRING, None, None, None, None, None),
        ("bar", DATETIME, None, None, None, None, None))

    cursor.connection.commit()
    assert cursor.description == (
        ("foo", STRING, None, None, None, None, None),
        ("bar", DATETIME, None, None, None, None, None))

    cursor.execute("insert into simple(key, val) values(3, 4)")
    assert cursor.description is None

    cursor.connection.commit()
    assert cursor.description is None

    cursor.execute("select key, val from simple")
    assert cursor.description == (
        ("key", NUMBER, None, None, None, None, None),
        ("val", NUMBER, None, None, None, None, None))

    cursor.connection.rollback()
    assert cursor.description == (
        ("key", NUMBER, None, None, None, None, None),
        ("val", NUMBER, None, None, None, None, None))

    with pytest.raises(ProgrammingError):
        cursor.execute("select")
    assert cursor.description is None


def test_binding_number_that_overflows_long_long():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    with pytest.raises(DataError):
        cursor.execute("select @i", dict(i=2**64+1))


def test_retrieving_null():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("select null, null")
    assert cursor.fetchall() == [[None, None]]


def test_retrieving_interval():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("select cast(0 as datetime) - cast(0 as datetime)")
    with pytest.raises(NotSupportedError):
        cursor.fetchone()


def test_syntax_error():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("foo")
    with pytest.raises(ProgrammingError):
        conn.rollback()


def test_errors_being_swallowed_during_cursor_close():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("foo")
    cursor.close()


def test_errors_being_swallowed_during_connection_close():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("foo")
    conn.close()


def test_error_from_closing_connection_twice():
    conn = connect('mattdb', 'dev')
    conn.close()
    with pytest.raises(InterfaceError):
        conn.close()


def test_misusing_cursor_objects():
    with pytest.raises(InterfaceError):
        conn = connect('mattdb', 'dev')
        cursor = conn.cursor()
        cursor.execute(" BEGIN TRANSACTION ")

    with pytest.raises(InterfaceError):
        conn = connect('mattdb', 'dev')
        cursor = conn.cursor()
        cursor.execute("commit")

    with pytest.raises(InterfaceError):
        conn = connect('mattdb', 'dev')
        cursor = conn.cursor()
        cursor.execute("  rollback   ")

    with pytest.raises(InterfaceError):
        conn = connect('mattdb', 'dev')
        cursor = conn.cursor()
        cursor.fetchone()

    with pytest.raises(InterfaceError):
        conn = connect('mattdb', 'dev')
        cursor = conn.cursor()
        cursor.fetchmany()

    with pytest.raises(InterfaceError):
        conn = connect('mattdb', 'dev')
        cursor = conn.cursor()
        cursor.fetchall()


def test_noop_methods():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.setinputsizes([1,2,3])
    cursor.setoutputsize(42)


def test_fetchmany():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()

    cursor.execute("select 1 UNION select 2 UNION select 3 order by 1")
    assert cursor.fetchmany() == [[1,]]
    assert cursor.fetchmany(2) == [[2,], [3,]]
    assert cursor.fetchmany(2) == []
    assert cursor.fetchmany(2) == []

    cursor.arraysize = 2
    cursor.execute("select 1 UNION select 2 UNION select 3 order by 1")
    assert cursor.fetchmany() == [[1,], [2,]]
    assert cursor.fetchmany() == [[3,]]

    cursor.arraysize = 4
    cursor.execute("select 1 UNION select 2 UNION select 3 order by 1")
    assert cursor.fetchmany() == [[1,], [2,], [3,]]


def test_consuming_result_sets_automatically():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("select 1 UNION select 2 UNION select 3 order by 1")
    cursor.execute("select 1 UNION select 2 UNION select 3 order by 1")


def test_inserting_non_utf8_string():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()

    cursor.execute("insert into strings values(cast(%(x)s as text), %(y)s)",
                   dict(x=b'\x68\xeb\x6c\x6c\x6f', y=b'\x68\xeb\x6c\x6c\x6f'))
    conn.commit()

    with pytest.raises(DataError):
        cursor.execute("select foo, bar from strings")
        rows = list(cursor)

    rows = list(cursor.execute("select cast(foo as blob), bar from strings"))
    assert rows == [[b'\x68\xeb\x6c\x6c\x6f', b'\x68\xeb\x6c\x6c\x6f']]


def test_cursor_connection_attribute_keeps_connection_alive():
    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    del conn
    cursor.execute("insert into simple(key, val) values(1, 2)")
    cursor.connection.commit()
    assert cursor.rowcount == 1

    cursor.execute("select key, val from simple order by key")
    assert cursor.fetchall() == [[1,2]]

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

def throw_on(expected_stmt, stmt, parameters=None):
    if stmt == expected_stmt:
        raise cdb2.Error(42, 'Not supported error')

@patch('comdb2.cdb2.Handle')
def test_begin_throws_error(handle):

    handle.return_value.execute.side_effect = functools.partial(throw_on, 'begin')

    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()

    with pytest.raises(OperationalError):
        cursor.execute("insert into simple(key, val) values(1, 2)")

@patch('comdb2.cdb2.Handle')
def test_commit_throws_error(handle):

    handle.return_value.execute.side_effect = functools.partial(throw_on, 'commit')

    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("insert into simple(key, val) values(1, 2)")

    with pytest.raises(OperationalError):
        conn.commit()

def raise_(ex):
    raise ex

@patch('comdb2.cdb2.Handle')
def test_get_effect_throws_error(handle):

    handle.return_value.get_effects.side_effect = lambda: raise_(cdb2.Error(42, 'Not supported error'))

    conn = connect('mattdb', 'dev')
    cursor = conn.cursor()
    cursor.execute("insert into simple(key, val) values(1, 2)")
    conn.commit()
