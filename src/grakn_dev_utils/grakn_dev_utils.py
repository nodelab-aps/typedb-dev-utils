from grakn.client import *
import py_dev_utils
#import itertools


def del_db(database, verbose=False, host="localhost", port="1729"):
    '''@usage delete a grakn database
    @param database: the database to delete, string
    @param verbose: whether to print databases after deletion, bool
    @param host, the host, string
    @param port, the port, string
    @return None
    '''
    with GraknClient.core(host+":"+port) as client:
        if client.databases().contains(database):
            client.databases().get(database).delete()
        else:
            print(database + " not found")
        if verbose:
            print("deleted " + database)
            print("databases: {}".format([db.name() for db in client.databases().all()]))


def init_db(
    database,
    gql_schema=None,
    parse_lines=False,
    verbose=False,
    host="localhost",
    port="1729"):
    '''
    @param database: the database to intialise, string
    @param gql_schema: path to schema, string
    @param parse_lines: whether to parse gql_schema line-by-line or as a whole. Bool, default False
    @param verbose: if True, print the define queries
    @param host, the host, string
    @param port, the port, string
    '''
    with GraknClient.core(host+":"+port) as client:
        client.databases().create(database)
        if not gql_schema is None:
            if parse_lines:
                f = open(gql_schema, "r")#
                with client.session(database, SessionType.SCHEMA) as session:
                    for line in f.readlines():
                        if all([token in line for token in ["define","sub",";"]]):
                            if verbose:
                                print(line)
                            with session.transaction(TransactionType.WRITE) as write_transaction:
                                write_transaction.query().define(line)
                                write_transaction.commit()
            else:
                query_define = open(gql_schema, "r").read()
                if verbose:
                    print(query_define)
                with client.session(database, SessionType.SCHEMA) as session:
                    with session.transaction(TransactionType.WRITE) as write_transaction:
                        write_transaction.query().define(query_define)
                        write_transaction.commit()
        if verbose:
            print("initiated " + database)
            print("databases: {}".format([db.name() for db in client.databases().all()]))


def ls_types(
    database,
    n=float("inf"),
    thingtypes=["entity","relation","attribute"],
    host="localhost",
    port="1729"):
    '''@usage print the types in a schema. Useful for getting a peak into the schema.
    @param database: the database to intialise, string
    @param n: the max number of each root type to print, default all
    @param thingtypes: the root types for which to print subtypes
    @param host, the host, string
    @param port, the port, string
    '''

    list_query_match = ["match $x sub {}; get $x;".format(thingtype) for thingtype in thingtypes]

    with GraknClient.core(host+":"+port) as client:
        with client.session(database, SessionType.SCHEMA) as session:
            with session.transaction(TransactionType.READ) as read_transaction:
                for i in range(len(list_query_match)):
                    query_match = list_query_match[i]
                    iterator_conceptMap = read_transaction.query().match(query_match)
                    k=0
                    print("===============")
                    print(thingtypes[i].upper())
                    print("===============")
                    for conceptMap in iterator_conceptMap:
                        if not conceptMap.get("x").get_label() in ["entity", "relation", "attribute"]:
                            print(conceptMap.get("x").get_label())
                            k+=1
                            if k==n:
                                break


def def_attr_type(
    database,
    new_attr_label,
    new_attr_value,
    sup_label="attribute",
    is_key=False,
    thingtypes = ["entity", "relation", "attribute"],
    verbose=False,
    host="localhost",
    port="1729"):
    '''@usage: add a new attribute to all or subset of ThingTypes
    @param database: the name of the database. string
    @param new_attr_label: the label of the new attribute. string
    @param new_attr_value: the value type of the new attribute, one of "long", "double", "string", "boolean" or "datetime". string
    @param sup: the supertype form which the new attributetype will inherit
    @param is_key: is the attribute a key, bool
    @param thingtypes: list of thing types which will own the attribute. Their subtypes will inherit.
    @param verbose: if True, print the define queries
    @param host: the host grakn is running on
    @param port: the port grakn is running on
    @return None
    '''

    list_query_match = ["match $x sub! {}; get $x;".format(thingtype) for thingtype in thingtypes]
    query_define_attr = "define {0} sub {1}, value {2};".format(new_attr_label, sup_label, new_attr_value)
    list_concept = []

    # get all the types in the schema
    with GraknClient.core(host+":"+port) as client:
        with client.session(database, SessionType.SCHEMA) as session:
            with session.transaction(TransactionType.READ) as read_transaction:
                for query_match in list_query_match:
                    iterator_conceptMap = read_transaction.query().match(query_match)
                    for conceptMap in iterator_conceptMap:
                        if not conceptMap.get("x").get_label() in ["entity", "relation", "attribute"]:
                            list_concept.append(conceptMap.get("x"))

            # define the new attribute
            with session.transaction(TransactionType.WRITE) as write_transaction:
                if verbose:
                    print(query_define_attr)
                write_transaction.query().define(query_define_attr)
                write_transaction.commit()

            # make existing types own the new attribute
            for concept in list_concept:
                with session.transaction(TransactionType.READ) as read_transaction:
                    concept_sup_label = concept.as_remote(read_transaction).get_supertype().get_label()
                with session.transaction(TransactionType.WRITE) as write_transaction:
                    query_define_owns = "define {0} sub {1},".format(concept.get_label(), concept_sup_label)
                    if concept.is_attribute_type():
                        valuetype = str(concept.get_value_type()).split(".")[1].lower()
                        query_define_owns += "value " + valuetype + ", "
                    query_define_owns += "owns {}".format(new_attr_label)
                    if is_key:
                        query_define_owns += " @key"
                    query_define_owns += ";"
                    if verbose:
                        print(query_define_owns)
                    write_transaction.query().define(query_define_owns)
                    write_transaction.commit()


def get_type_owns(
    database,
    thingtype,
    host="localhost",
    port="1729"):
    '''@usage get the attribute types owned by thingtype
    @param database: the database, string
    @param thingtype: the thingtype for which to retrieve attributes, string
    @param host: the host grakn is running on
    @param port: the port grakn is running on
    @return dict of string {"attr1":valuetype, "attr2":valuetype, ... "@key":"attr1"}
            where the "@key" key returns the name of the key attribute (if it exists)
    '''
    query_thingtype = "match $x type {}; get $x;".format(thingtype)
    dict_out = {}

    with GraknClient.core(host+":"+port) as client:
        with client.session(database, SessionType.SCHEMA) as session:
            with session.transaction(TransactionType.READ) as read_transaction:
                iterator_conceptMap = read_transaction.query().match(query_thingtype)
                concept = next(iterator_conceptMap).get("x")
                iterator_attr = concept.as_remote(read_transaction).get_owns(value_type=None, keys_only=False)
                for attrtype in iterator_attr:
                    dict_out[attrtype.get_label()] = str(attrtype.get_value_type()).split(".")[1].lower()
                iterator_key = concept.as_remote(read_transaction).get_owns(value_type=None, keys_only=True)
                iterator_key = py_dev_utils.check_whether_iterator_empty(iterator_key)
                if not iterator_key is None:
                    dict_out["@key"] = next(iterator_key).get_label()
    return dict_out


def def_rel_type(
    database,
    new_rel_label,
    dict_role_players,
    rel_sup="relation",
    verbose=False,
    host="localhost",
    port="1729"):
    '''@usage: add a new relationtype to the schema
    @param database: the name of the database. string
    @param new_rel_label: the label of the new relation type. string
    @param dict_role_players: dict
            keys: role labels (string)
            values: dict
                key-values:
                    "role_players": array of role_player types (string)
                    "role_sup": role supertype label ("role" if inheriting from root Role)
           to make a role applicable to all descendents of one or more root types, provide one or more of the root type(s) ["entity", "relation", "attribute"]
    @param rel_sup: the supertype form which the new relationtype will inherit
    @param verbose: if True, print the define queries
    @param host: the host grakn is running on
    @param port: the port grakn is running on
    @return None
    '''

    with GraknClient.core(host+":"+port) as client:
        with client.session(database, SessionType.SCHEMA) as session:
            # check if any root types included
            for role_label in dict_role_players.keys():
                list_role_players = dict_role_players[role_label]["role_players"]
                role_sup_label = dict_role_players[role_label]["role_sup"]
                for root_type in ["entity", "relation", "attribute"]:
                    if root_type in list_role_players:
                        with session.transaction(TransactionType.READ) as read_transaction:
                            query_sub = "match $x sub {}; get $x;".format(root_type)
                            iterator_conceptMap = read_transaction.query().match(query_sub)
                            for conceptMap in iterator_conceptMap:
                                dict_role_players[role_label]["role_players"].append(conceptMap.get("x").get_label())
                        # remove the root type from the role players
                        idx = dict_role_players[role_label]["role_players"].index(root_type)
                        dict_role_players[role_label]["role_players"].pop(idx)

            # prepare define relation query
            query_define_rel = "define {0} sub {1}, ".format(new_rel_label, rel_sup)
            list_clause_relates = ["relates {} as {}".format(role, dict_role_players[role]["role_sup"]) for role in dict_role_players.keys()]
            query_define_rel += ", ".join(list_clause_relates) + ";"

            with session.transaction(TransactionType.WRITE) as write_transaction:
                # define relation type
                if verbose:
                    print(query_define_rel)
                write_transaction.query().define(query_define_rel)
                write_transaction.commit()

            # add "plays" to existing types
            for role_label, dict_role_player in dict_role_players.items():
                for role_player_label in dict_role_player["role_players"]:
                    # get sup
                    with session.transaction(TransactionType.READ) as read_transaction:
                        role_player_concept = read_transaction.concepts().get_thing_type(role_player_label)
                        rp_sup_label = role_player_concept.as_remote(read_transaction).get_supertype().get_label()
                    query_define_plays = "define {0} sub {1}, plays {2}:{3};".format(role_player_label, rp_sup_label, new_rel_label, role_label)
                    with session.transaction(TransactionType.WRITE) as write_transaction:
                        if verbose:
                            print(query_define_plays)
                        write_transaction.query().define(query_define_plays)
                        write_transaction.commit()


def get_type_plays(
    database,
    thingtype,
    host="localhost",
    port="1729"):
    '''@usage get the roles played by thingtype
    @param database: the database, string
    @param thingtype: the thingtype for which to retrieve attributes, string
    @param host: the host grakn is running on
    @param port: the port grakn is running on
    @return list of string ["rel1:role1", "rel1:role2", "rel2:role3"..]
    '''
    query_thingtype = "match $x type {}; get $x;".format(thingtype)
    list_out = []

    with GraknClient.core(host+":"+port) as client:
        with client.session(database, SessionType.SCHEMA) as session:
            with session.transaction(TransactionType.READ) as read_transaction:
                iterator_conceptMap = read_transaction.query().match(query_thingtype)
                concept = next(iterator_conceptMap).get("x")
                iterator_roletype = concept.as_remote(read_transaction).get_plays()
                for roletype in iterator_roletype:
                    list_out.append(roletype.get_scoped_label())

    list_out.sort()
    return list_out


def insert_data(
    database,
    gql_data,
    parse_lines=False,
    line_modifier = lambda line: line,
    verbose=False,
    host="localhost",
    port="1729"):
    '''
    @param database: the database to intialise, string
    @param gql_data: path to data, string
    @param parse_lines: whether to parse gql_data line-by-line or as a whole. bool, default False
    @param verbose: if True, print the insert queries
    @param line_modifier: if parse_lines, optionally pre-process each line using a provided function that takes a string input and returns the modified line.
    @param host, the host, string
    @param port, the port, string
    '''
    with GraknClient.core(host+":"+port) as client:
        if parse_lines:
            f = open(gql_data, "r")
            with client.session(database, SessionType.DATA) as session:
                for line in f.readlines():
                    if all([token in line for token in ["insert",";"]]) and not line.rstrip()[0]=="#":
                        line = line_modifier(line)
                        if verbose:
                            print(line)
                        with session.transaction(TransactionType.WRITE) as write_transaction:
                            write_transaction.query().insert(line)
                            write_transaction.commit()
        else:
            query_insert = open(gql_data, "r").read()
            if verbose:
                print(query_insert)
            with client.session(database, SessionType.DATA) as session:
                with session.transaction(TransactionType.WRITE) as write_transaction:
                    write_transaction.query().insert(query_insert)
                    write_transaction.commit()
        if verbose:
            print("databases: {}".format(client.databases().all()))


def ls_instances(
    database,
    n=10,
    thingtypes=["entity","relation","attribute"],
    print_attributes = True,
    print_relations = True,
    host="localhost",
    port="1729"):
    '''@usage print the top n instances of each root type, along with an attribute and a relation.
              useful for getting a peak into the data
    @param database: the database to intialise, string
    @param n: the max number of each type to print, default all
    @param thingtypes: the types for which to print subtypes
    @param print_attributes: print the attributes owned by the type, if any
    @param print_relations: print the relations in which instance plays a role, if any
    @param host, the host, string
    @param port, the port, string
    '''

    list_query_match = ["match $x isa {}; ".format(thingtype) for thingtype in thingtypes]
    get_clause = "get $x"
    if print_attributes:
        list_query_match = [query_match + "$x has attribute $attr; " for query_match in list_query_match]
        get_clause += ", $attr"
    if print_relations:
        list_query_match = [query_match + "$rel ($role:$x) isa relation; " for query_match in list_query_match]
        get_clause += ", $rel, $role"
    get_clause += ";"
    list_query_match = [query_match + get_clause for query_match in list_query_match]

    with GraknClient.core(host+":"+port) as client:
        with client.session(database, SessionType.DATA) as session:
            with session.transaction(TransactionType.READ) as read_transaction:
                for i in range(len(list_query_match)):
                    query_match = list_query_match[i]
                    iterator_conceptMap = read_transaction.query().match(query_match)
                    iterator_conceptMap = py_dev_utils.check_whether_iterator_empty(iterator_conceptMap)
                    if not iterator_conceptMap is None:
                        k=0
                        print("===============")
                        print(thingtypes[i].upper())
                        print("===============")
                        for conceptMap in iterator_conceptMap:
                            dict_concept = conceptMap.map()
                            concept = dict_concept["x"]
                            iid = concept.get_iid()
                            type_label = concept.as_remote(read_transaction).get_type().get_label()
                            line_print = "$x iid {0} isa {1}; ".format(iid, type_label)
                            if print_attributes:
                                concept_attr = dict_concept["attr"]
                                attr_value = str(concept_attr.get_value())
                                attr_type_label = concept_attr.as_remote(read_transaction).get_type().get_label()
                                line_print += "$attr {0} isa {1}; ".format(attr_value, attr_type_label)
                            if print_relations:
                                # relation
                                concept_rel = dict_concept["rel"]
                                rel_iid = concept_rel.get_iid()
                                rel_type_label = concept_rel.as_remote(read_transaction).get_type().get_label()
                                # role
                                concept_role = dict_concept["role"]
                                role_label = concept_role.get_label()
                                line_print += "$rel iid {0} ({1}:$x) isa {2}; ".format(rel_iid, role_label, rel_type_label)

                            print(line_print)
                            k+=1
                            if k==n:
                                break


def modify_things(
    database,
    query_match = "match $x isa thing; get $x;",
    thing_modifier = lambda write_transaction, thing : None,
    args=None,
    host="localhost",
    port="1729"):
    '''@usage: iterate over all non-root things matching query, calling thing_modifier
    @param database: the name of the database. string
    @param thing_modifier: a function that takes a write transaction and a thing as first and second argument.
                Additional positional arguments can be passed through args.
                Optionally returns value
    @param args: a list of additional positional arguments to pass to thing_modifier after thing
    @param host: the host grakn is running on
    @param port: the port grakn is running on
    @return a list of values returned by thing_modifier (if None returned, list of None)
    '''

    list_out = []
    with GraknClient.core(host+":"+port) as client:
        with client.session(database, SessionType.DATA) as session:
            with session.transaction(TransactionType.READ) as read_transaction:
                iterator_conceptMap = read_transaction.query().match(query_match)
                for conceptMap in iterator_conceptMap:
                    with session.transaction(TransactionType.WRITE) as write_transaction:
                        thing = conceptMap.get("x")
                        result = thing_modifier(write_transaction, thing, *args) if args else list_out.append(thing_modifier(write_transaction,thing))
                        list_out.append(result)
                        write_transaction.commit()
    return list_out