import os
import sys
import unittest
import warnings

if os.path.basename(os.getcwd()) == "test":
    sys.path.insert(1, "..")
else:
    sys.path.insert(1, ".")

from kafi.kafka.restproxy.restproxy import *
from kafi.kafka.cluster.cluster import *
from kafi.helpers import *

config_str = "local"
principal_str = None
# config_str = "ccloud"
# principal_str = "User:admin"

OFFSET_INVALID = -1001

class Test(unittest.TestCase):
    def setUp(self):
        warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
        #
        # https://simon-aubury.medium.com/kafka-with-avro-vs-kafka-with-protobuf-vs-kafka-with-json-schema-667494cbb2af
        self.snack_str_list = ['{"name": "cookie", "calories": 500.0, "colour": "brown"}', '{"name": "cake", "calories": 260.0, "colour": "white"}', '{"name": "timtam", "calories": 80.0, "colour": "chocolate"}']
        self.snack_bytes_list = [bytes(snack_str, encoding="utf-8") for snack_str in self.snack_str_list]
        self.snack_dict_list = [json.loads(snack_str) for snack_str in self.snack_str_list]
        #
        self.snack_ish_dict_list = []
        for snack_dict in self.snack_dict_list:
            snack_dict1 = snack_dict.copy()
            snack_dict1["colour"] += "ish"
            self.snack_ish_dict_list.append(snack_dict1)
        #
        self.avro_schema_str = '{ "type": "record", "name": "myrecord", "fields": [{"name": "name",  "type": "string" }, {"name": "calories", "type": "float" }, {"name": "colour", "type": "string" }] }'
        self.protobuf_schema_str = 'message Snack { required string name = 1; required float calories = 2; optional string colour = 3; }'
        self.jsonschema_schema_str = '{ "title": "abc", "definitions" : { "record:myrecord" : { "type" : "object", "required" : [ "name", "calories" ], "additionalProperties" : false, "properties" : { "name" : {"type" : "string"}, "calories" : {"type" : "number"}, "colour" : {"type" : "string"} } } }, "$ref" : "#/definitions/record:myrecord" }'
        #
        self.topic_str_list = []
        self.group_str_list = []
        #
        print("Test:", self._testMethodName)

    def tearDown(self):
        consumer = RestProxy(config_str)
        for topic_str in self.topic_str_list:
            consumer.delete(topic_str)

    def create_test_topic_name(self):
        while True:
            topic_str = f"test_topic_{get_millis()}"
            #
            if topic_str not in self.topic_str_list:
                self.topic_str_list.append(topic_str)
                break
        #
        return topic_str

    def create_test_group_name(self):
        while True:
            group_str = f"test_group_{get_millis()}"
            #
            if group_str not in self.group_str_list:
                self.group_str_list.append(group_str)
                break
        #
        return group_str

    ### RestProxyAdmin
    # ACLs

    def test_acls(self):
        if principal_str:
            consumer = RestProxy(config_str)
            topic_str = self.create_test_topic_name()
            consumer.create(topic_str)
            consumer.create_acl(restype="topic", name=topic_str, resource_pattern_type="literal", principal=principal_str, host="*", operation="read", permission_type="allow")
            acl_dict_list = consumer.acls()
            self.assertIn({"restype": "topic", "name": topic_str, "resource_pattern_type": "literal", 'principal': principal_str, 'host': '*', 'operation': 'read', 'permission_type': 'ALLOW'}, acl_dict_list)
            consumer.delete_acl(restype="topic", name=topic_str, resource_pattern_type="literal", principal=principal_str, host="*", operation="read", permission_type="allow")
            self.assertIn({"restype": "topic", "name": topic_str, "resource_pattern_type": "literal", 'principal': principal_str, 'host': '*', 'operation': 'read', 'permission_type': 'ALLOW'}, acl_dict_list)
            consumer.delete(topic_str)

    # Brokers
    
    def test_brokers(self):
        consumer = RestProxy(config_str)
        if "confluent.cloud" not in consumer.rest_proxy_config_dict["rest.proxy.url"]: # cannot modify cluster properties of non-dedicated Confluent Cloud test cluster
            broker_dict = consumer.brokers()
            broker_int = list(broker_dict.keys())[0]
            broker_dict1 = consumer.brokers(f"{broker_int}")
            self.assertEqual(broker_dict, broker_dict1)
            broker_dict2 = consumer.brokers([broker_int])
            self.assertEqual(broker_dict1, broker_dict2)
            broker_int = list(broker_dict.keys())[0]
            broker_int_broker_config_dict = consumer.broker_config(broker_int)
            if "background.threads" in broker_int_broker_config_dict[broker_int]:
                old_background_threads_str = broker_int_broker_config_dict[broker_int]["background.threads"]
            else:
                old_background_threads_str = "10"
            consumer.set_broker_config({"background.threads": 5}, broker_int)
            new_background_threads_str = consumer.broker_config(broker_int)[broker_int]["background.threads"]
            self.assertEqual(new_background_threads_str, "5")
            consumer.set_broker_config({"background.threads": old_background_threads_str}, broker_int)

    # Groups

    def test_groups(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str)
        producer.produce("message 1")
        producer.produce("message 2")
        producer.produce("message 3")
        producer.close()
        #
        group_str = self.create_test_group_name()
        consumer = r.consumer(topic_str, group=group_str)
        consumer.consume()
        #
        group_str_list1 = consumer.groups(["test*", "test_group*"])
        self.assertIn(group_str, group_str_list1)
        group_str_list2 = consumer.groups("test_group*")
        self.assertIn(group_str, group_str_list2)
        group_str_list3 = consumer.groups("test_group*", state_pattern=["stable"])
        self.assertIn(group_str, group_str_list3)
        group_str_state_str_dict = consumer.groups("test_group*", state_pattern="stab*", state=True)
        self.assertIn("stable", group_str_state_str_dict[group_str])
        group_str_list4 = consumer.groups(state_pattern="unknown", state=False)
        self.assertEqual(group_str_list4, [])
        #
        consumer.close()

    def test_describe_groups(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str)
        producer.produce("message 1")
        producer.produce("message 2")
        producer.produce("message 3")
        producer.close()
        #
        group_str = self.create_test_group_name()
        consumer = r.consumer(topic_str, group=group_str)
        consumer.consume()
        #
        group_dict = consumer.describe_groups(group_str)[group_str]
        self.assertEqual(group_dict["group_id"], group_str)
        self.assertEqual(group_dict["is_simple_consumer_group"], False)
        self.assertEqual(group_dict["members"][0]["client_id"][:len(f"consumer-{group_str}")], f"consumer-{group_str}")
        self.assertIsNone(group_dict["members"][0]["group_instance_id"])
        self.assertEqual(group_dict["partition_assignor"], "range")
        self.assertEqual(group_dict["state"], "stable")
        broker_dict = consumer.brokers()
        broker_int = list(broker_dict.keys())[0]
        #
        consumer.close()

    def test_group_offsets(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str, partitions=2)
        producer = consumer.producer(topic_str)
        producer.produce("message 1", partition=0)
        producer.produce("message 2", partition=1)
        producer.close()
        #
        group_str = self.create_test_group_name()
        consumer = r.consumer(topic_str, group=group_str, config={"enable.auto.commit": False})
        consumer.consume()
        consumer.commit()
        consumer.consume()
        consumer.commit()
        #
        group_str_topic_str_partition_int_offset_int_dict_dict_dict = consumer.group_offsets(group_str)
        self.assertIn(group_str, group_str_topic_str_partition_int_offset_int_dict_dict_dict)
        self.assertIn(topic_str, group_str_topic_str_partition_int_offset_int_dict_dict_dict[group_str])
        self.assertEqual(group_str_topic_str_partition_int_offset_int_dict_dict_dict[group_str][topic_str][0], 1)
        self.assertEqual(group_str_topic_str_partition_int_offset_int_dict_dict_dict[group_str][topic_str][1], 1)
        #
        consumer.unsubscribe()
        consumer.close()

    # Topics

    def test_config_set_config(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.touch(topic_str)
        #
        consumer.set_config(topic_str, {"retention.ms": 4711})
        new_retention_ms_str = consumer.config(topic_str)[topic_str]["retention.ms"]
        self.assertEqual(new_retention_ms_str, "4711")

    def test_create_delete(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.touch(topic_str)
        topic_str_list = consumer.ls()
        self.assertIn(topic_str, topic_str_list)
        consumer.rm(topic_str)
        topic_str_list = consumer.ls()
        self.assertNotIn(topic_str, topic_str_list)

    def test_topics(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        old_topic_str_list = consumer.topics(["test_*"])
        self.assertNotIn(topic_str, old_topic_str_list)
        consumer.create(topic_str)
        new_topic_str_list = consumer.ls(["test_*"])
        self.assertIn(topic_str, new_topic_str_list)
        #
        producer = consumer.producer(topic_str)
        producer.produce("message 1")
        producer.produce("message 2")
        producer.produce("message 3")
        producer.close()
        #
        topic_str_size_int_dict_l = consumer.l(pattern=topic_str)
        topic_str_size_int_dict_ll = consumer.ll(pattern=topic_str)
        self.assertEqual(topic_str_size_int_dict_l, topic_str_size_int_dict_ll)
        size_int = topic_str_size_int_dict_l[topic_str]
        self.assertEqual(size_int, 3)
        topic_str_size_int_partitions_dict_dict = consumer.topics(pattern=topic_str, size=True, partitions=True)
        self.assertEqual(topic_str_size_int_partitions_dict_dict[topic_str]["size"], 3)
        self.assertEqual(topic_str_size_int_partitions_dict_dict[topic_str]["partitions"][0], 3)
        topic_str_partitions_dict_dict = consumer.l(pattern=topic_str, size=False, partitions=True)
        self.assertEqual(topic_str_partitions_dict_dict[topic_str][0], 3)

    def test_partitions_set_partitions(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str, partitions=2)
        partitions_int1 = consumer.partitions(topic_str)[topic_str]
        self.assertEqual(partitions_int1, 2)
        topic_str_partition_int_partition_dict_dict_dict = consumer.partitions(topic_str, verbose=True)[topic_str]
        self.assertEqual(list(topic_str_partition_int_partition_dict_dict_dict.keys()), [0, 1])
        self.assertEqual(topic_str_partition_int_partition_dict_dict_dict[0]["leader"], 1)
        self.assertEqual(topic_str_partition_int_partition_dict_dict_dict[0]["replicas"], [1])
        self.assertEqual(topic_str_partition_int_partition_dict_dict_dict[0]["isrs"], [1])
        self.assertEqual(topic_str_partition_int_partition_dict_dict_dict[1]["leader"], 1)
        self.assertEqual(topic_str_partition_int_partition_dict_dict_dict[1]["replicas"], [1])
        self.assertEqual(topic_str_partition_int_partition_dict_dict_dict[1]["isrs"], [1])

    def test_exists(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        self.assertFalse(r.exists(topic_str))
        consumer.create(topic_str)
        self.assertTrue(r.exists(topic_str))

    # Produce/Consume

    def test_produce_consume_bytes_str(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        # Upon produce, the types "bytes" and "string" trigger the conversion of bytes, strings and dictionaries to bytes on Kafka.
        producer = consumer.producer(topic_str, key_type="bytes", value_type="str")
        producer.produce(self.snack_str_list, key=self.snack_str_list)
        producer.close()
        self.assertEqual(r.topics(topic_str, size=True, partitions=True)[topic_str]["size"], 3)
        #
        group_str = self.create_test_group_name()
        # Upon consume, the type "str" triggers the conversion into a string, and "bytes" into bytes.
        consumer = r.consumer(topic_str, group=group_str, key_type="str", value_type="bytes")
        message_dict_list = consumer.consume(n=3)
        key_str_list = [message_dict["key"] for message_dict in message_dict_list]
        value_bytes_list = [message_dict["value"] for message_dict in message_dict_list]
        self.assertEqual(key_str_list, self.snack_str_list)
        self.assertEqual(value_bytes_list, self.snack_bytes_list)
        consumer.close()

    def test_produce_consume_json(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        # Upon produce, the type "json" triggers the conversion of bytes, strings and dictionaries to bytes on Kafka.
        producer = consumer.producer(topic_str, key_type="json", value_type="json")
        producer.produce(self.snack_dict_list, key=self.snack_str_list)
        producer.close()
        self.assertEqual(r.topics(topic_str, size=True, partitions=True)[topic_str]["size"], 3)
        #
        group_str = self.create_test_group_name()
        # Upon consume, the type "json" triggers the conversion into a dictionary.
        consumer = r.consumer(topic_str, group=group_str, key_type="json", value_type="json")
        message_dict_list = consumer.consume(n=3)
        key_dict_list = [message_dict["key"] for message_dict in message_dict_list]
        value_dict_list = [message_dict["value"] for message_dict in message_dict_list]
        self.assertEqual(key_dict_list, self.snack_dict_list)
        self.assertEqual(value_dict_list, self.snack_dict_list)
        consumer.close()

    def test_produce_consume_protobuf(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        # Upon produce, the type "protobuf" (alias = "pb") triggers the conversion of bytes, strings and dictionaries into Protobuf-encoded bytes on Kafka.
        producer = consumer.producer(topic_str, key_type="protobuf", value_type="pb", key_schema=self.protobuf_schema_str, value_schema=self.protobuf_schema_str)
        producer.produce(self.snack_dict_list, key=self.snack_str_list)
        producer.close()
        self.assertEqual(r.topics(topic_str, size=True, partitions=True)[topic_str]["partitions"][0], 3)
        #
        group_str = self.create_test_group_name()
        # Upon consume, the type "protobuf" (alias = "pb") triggers the conversion into a dictionary.
        consumer = r.consumer(topic_str, group=group_str, key_type="pb", value_type="protobuf")
        message_dict_list = consumer.consume(n=3)
        key_dict_list = [message_dict["key"] for message_dict in message_dict_list]
        value_dict_list = [message_dict["value"] for message_dict in message_dict_list]
        self.assertEqual(key_dict_list, self.snack_dict_list)
        self.assertEqual(value_dict_list, self.snack_dict_list)
        consumer.close()

    def test_produce_consume_avro(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        # Upon produce, the type "avro" triggers the conversion of bytes, strings and dictionaries into Avro-encoded bytes on Kafka.
        producer = consumer.producer(topic_str, key_type="avro", value_type="avro", key_schema=self.avro_schema_str, value_schema=self.avro_schema_str)
        producer.produce(self.snack_dict_list, key=self.snack_bytes_list)
        producer.close()
        self.assertEqual(r.topics(topic_str, size=True, partitions=True)[topic_str]["partitions"][0], 3)
        #
        group_str = self.create_test_group_name()
        # Upon consume, the types "protobuf" (alias = "pb") and "avro" trigger the conversion into a dictionary.
        consumer = r.consumer(topic_str, group=group_str, key_type="avro", value_type="avro")
        message_dict_list = consumer.consume(n=3)
        key_dict_list = [message_dict["key"] for message_dict in message_dict_list]
        value_dict_list = [message_dict["value"] for message_dict in message_dict_list]
        self.assertEqual(key_dict_list, self.snack_dict_list)
        self.assertEqual(value_dict_list, self.snack_dict_list)
        consumer.close()

    def test_produce_consume_jsonschema(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        # Upon produce, the type "jsonschema" triggers the conversion of bytes, strings and dictionaries into JSONSchema-encoded bytes on Kafka.
        producer = consumer.producer(topic_str, key_type="json_sr", value_type="jsonschema", key_schema=self.jsonschema_schema_str, value_schema=self.jsonschema_schema_str)
        producer.produce(self.snack_dict_list, key=self.snack_str_list)
        producer.close()
        self.assertEqual(r.topics(topic_str, size=True, partitions=True)[topic_str]["partitions"][0], 3)
        #
        group_str = self.create_test_group_name()
        # Upon consume, the type "jsonschema" (alias = "json_sr") triggers the conversion into a dictionary.
        consumer = r.consumer(topic_str, group=group_str, key_type="jsonschema", value_type="json_sr")
        message_dict_list = consumer.consume(n=3)
        key_dict_list = [message_dict["key"] for message_dict in message_dict_list]
        value_dict_list = [message_dict["value"] for message_dict in message_dict_list]
        self.assertEqual(key_dict_list, self.snack_dict_list)
        self.assertEqual(value_dict_list, self.snack_dict_list)
        consumer.close()

    def test_commit(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str)
        producer.produce("message 1")
        producer.produce("message 2")
        producer.produce("message 3")
        producer.close()
        #
        group_str = self.create_test_group_name()
        consumer = r.consumer(topic_str, group=group_str, config={"enable.auto.commit": "False"})
        consumer.consume()
        offsets_dict = consumer.offsets()
        self.assertEqual(offsets_dict, {})
        consumer.commit()
        offsets_dict1 = consumer.offsets()
        self.assertEqual(offsets_dict1[topic_str][0], 3)
        consumer.close()
    
    def test_cluster_settings(self):
        consumer = RestProxy(config_str)
        #
        consumer.verbose(0)
        self.assertEqual(r.verbose(), 0)

    def test_configs(self):
        consumer = RestProxy(config_str)
        #
        config_str_list1 = consumer.configs()
        self.assertIn("local", config_str_list1)
        config_str_list2 = consumer.configs("loc*")
        self.assertIn("local", config_str_list2)
        config_str_list3 = consumer.configs("this_pattern_shall_not_match_anything")
        self.assertEqual(config_str_list3, [])
        #
        config_str_config_dict_dict = consumer.configs(verbose=True)
        self.assertIn("local", config_str_config_dict_dict)
        self.assertEqual(True, config_str_config_dict_dict["local"]["kafi"]["enable.auto.commit"])

    # Shell

    # Shell.cat -> Functional.map -> Functional.flatmap -> Functional.foldl -> RestProxyConsumer.consumer/KafkaConsumer.foldl/RestProxyConsumer.close -> RestProxyConsumer.consume
    def test_cat(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str)
        producer.produce(self.snack_str_list)
        producer.close()
        #
        group_str = self.create_test_group_name()
        (message_dict_list, n_int) = consumer.cat(topic_str, group=group_str)
        self.assertEqual(3, len(message_dict_list))
        self.assertEqual(3, n_int)
        value_str_list = [message_dict["value"] for message_dict in message_dict_list]
        self.assertEqual(value_str_list, self.snack_str_list)

    # Shell.head -> Shell.cat
    def test_head(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str, value_type="avro", value_schema=self.avro_schema_str)
        producer.produce(self.snack_str_list)
        producer.close()
        #
        group_str = self.create_test_group_name()
        (message_dict_list, n_int) = consumer.head(topic_str, group=group_str, type="avro")
        self.assertEqual(3, len(message_dict_list))
        self.assertEqual(3, n_int)
        value_dict_list = [message_dict["value"] for message_dict in message_dict_list]
        self.assertEqual(value_dict_list, self.snack_dict_list)

    # Shell.tail -> Functional.map -> Functional.flatmap -> Functional.foldl -> RestProxyConsumer.consumer/KafkaConsumer.foldl/RestProxyConsumer.close -> RestProxyConsumer.consume
    def test_tail(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str, value_type="protobuf", value_schema=self.protobuf_schema_str)
        producer.produce(self.snack_dict_list)
        producer.close()
        #
        group_str = self.create_test_group_name()
        (message_dict_list, n_int) = consumer.tail(topic_str, group=group_str, type="pb")
        self.assertEqual(3, len(message_dict_list))
        self.assertEqual(3, n_int)
        value_dict_list = [message_dict["value"] for message_dict in message_dict_list]
        self.assertEqual(value_dict_list, self.snack_dict_list)

    # Shell.cp -> Functional.map_to -> Functional.flatmap_to -> RestProxyConsumer.producer/Functional.foldl/RestProxyConsumer.close -> RestProxyConsumer.consumer/KafkaConsumer.foldl/RestProxyConsumer.close -> RestProxyConsumer.consume
    def test_cp(self):
        print(self.topic_str_list)
        consumer = RestProxy(config_str)
        #
        topic_str1 = self.create_test_topic_name()
        consumer.create(topic_str1)
        producer = consumer.producer(topic_str1, value_type="json_sr", value_schema=self.jsonschema_schema_str)
        producer.produce(self.snack_bytes_list)
        producer.close()
        topic_str2 = self.create_test_topic_name()
        #
        def map_ish(message_dict):
            message_dict["value"]["colour"] += "ish"
            return message_dict
        #
        group_str1 = self.create_test_group_name()
        (consume_n_int, written_n_int) = r.cp(topic_str1, r, topic_str2, group=group_str1, source_type="jsonschema", target_type="json", produce_batch_size=2, map_function=map_ish, n=3)
        self.assertEqual(3, consume_n_int)
        self.assertEqual(3, written_n_int)
        #
        group_str2 = self.create_test_group_name()
        (message_dict_list2, n_int2) = consumer.cat(topic_str2, group=group_str2, type="json")
        self.assertEqual(3, len(message_dict_list2))
        self.assertEqual(3, n_int2)
        value_dict_list2 = [message_dict2["value"] for message_dict2 in message_dict_list2]
        self.assertEqual(value_dict_list2, self.snack_ish_dict_list)

    def test_wc(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str, value_type="protobuf", value_schema=self.protobuf_schema_str)
        producer.produce(self.snack_dict_list)
        producer.close()
        #
        group_str1 = self.create_test_group_name()
        (num_messages_int, acc_num_words_int, acc_num_bytes_int) = consumer.wc(topic_str, group=group_str1, type="pb")
        self.assertEqual(3, num_messages_int)
        self.assertEqual(18, acc_num_words_int)
        self.assertEqual(169, acc_num_bytes_int)

    # Shell.diff -> Shell.diff_fun -> Functional.zipfoldl -> RestProxyConsumer.consumer/read/close
    def test_diff(self):
        consumer = RestProxy(config_str)
        #
        topic_str1 = self.create_test_topic_name()
        consumer.create(topic_str1)
        w1 = consumer.producer(topic_str1, value_type="protobuf", value_schema=self.protobuf_schema_str)
        w1.produce(self.snack_str_list)
        w1.close()
        #
        topic_str2 = self.create_test_topic_name()
        consumer.create(topic_str2)
        w2 = consumer.producer(topic_str2, value_type="avro", value_schema=self.avro_schema_str)
        w2.produce(self.snack_ish_dict_list)
        w2.close()
        #
        group_str1 = self.create_test_group_name()
        group_str2 = self.create_test_group_name()
        (message_dict_message_dict_tuple_list, message_counter_int1, message_counter_int2) = consumer.diff(topic_str1, r, topic_str2, group1=group_str1, group2=group_str2, type1="pb", type2="avro")
        self.assertEqual(3, len(message_dict_message_dict_tuple_list))
        self.assertEqual(3, message_counter_int1)
        self.assertEqual(3, message_counter_int2)

    # Shell.diff -> Shell.diff_fun -> Functional.flatmap -> Functional.foldl -> RestProxyConsumer.open/Kafka.foldl/RestProxyConsumer.close -> RestProxyConsumer.consume 
    def test_grep(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str, value_type="protobuf", value_schema=self.protobuf_schema_str)
        producer.produce(self.snack_str_list)
        producer.close()
        #
        group_str = self.create_test_group_name()
        (message_dict_message_dict_tuple_list, message_counter_int1, message_counter_int2) = consumer.grep(topic_str, ".*brown.*", group=group_str, type="pb")
        self.assertEqual(1, len(message_dict_message_dict_tuple_list))
        self.assertEqual(1, message_counter_int1)
        self.assertEqual(3, message_counter_int2)
    
    # Functional

    def test_foreach(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str, value_type="jsonschema", value_schema=self.jsonschema_schema_str)
        producer.produce(self.snack_str_list)
        producer.close()
        #
        colour_str_list = []
        group_str = self.create_test_group_name()
        consumer.foreach(topic_str, group=group_str, foreach_function=lambda message_dict: colour_str_list.append(message_dict["value"]["colour"]), type="jsonschema")
        self.assertEqual("brown", colour_str_list[0])
        self.assertEqual("white", colour_str_list[1])
        self.assertEqual("chocolate", colour_str_list[2])

    def test_filter(self):
        consumer = RestProxy(config_str)
        #
        topic_str = self.create_test_topic_name()
        consumer.create(topic_str)
        producer = consumer.producer(topic_str, value_type="avro", value_schema=self.avro_schema_str)
        producer.produce(self.snack_str_list)
        producer.close()
        #
        group_str = self.create_test_group_name()
        (message_dict_list, message_counter_int) = consumer.filter(topic_str, group=group_str, filter_function=lambda message_dict: message_dict["value"]["calories"] > 100, type="avro")
        self.assertEqual(2, len(message_dict_list))
        self.assertEqual(3, message_counter_int)

    def test_filter_to(self):
        consumer = RestProxy(config_str)
        #
        topic_str1 = self.create_test_topic_name()
        consumer.create(topic_str1)
        producer = consumer.producer(topic_str1, value_type="avro", value_schema=self.avro_schema_str)
        producer.produce(self.snack_str_list)
        producer.close()
        #
        topic_str2 = self.create_test_topic_name()
        #
        group_str1 = self.create_test_group_name()
        (consume_n_int, written_n_int) = r.filter_to(topic_str1, r, topic_str2, group=group_str1, filter_function=lambda message_dict: message_dict["value"]["calories"] > 100, source_type="avro", target_type="json")
        self.assertEqual(3, consume_n_int)
        self.assertEqual(2, written_n_int)
        #
        group_str2 = self.create_test_group_name()
        (message_dict_list, n_int) = consumer.cat(topic_str2, group=group_str2, type="json")
        self.assertEqual(2, len(message_dict_list))
        self.assertEqual(2, n_int)
        self.assertEqual(500.0, message_dict_list[0]["value"]["calories"])
        self.assertEqual(260.0, message_dict_list[1]["value"]["calories"])
