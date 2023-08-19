import ast
import json
import os

from kafi.storage_reader import StorageReader

# Constants

ALL_MESSAGES = -1

#

class FSReader(StorageReader):
    def __init__(self, fs_obj, *topics, **kwargs):
        super().__init__(fs_obj, *topics, **kwargs)
        #
        if isinstance(self.topic_str_list, list) and len(self.topic_str_list) > 1:
            raise Exception("Reading from multiple topics is not supported.")
        #
        self.topic_str = self.topic_str_list[0]
        #
        self.partition_int_offset_int_dict = self.topic_str_offsets_dict_dict[self.topic_str] if self.topic_str_offsets_dict_dict is not None else None

    #
    
    def foldl(self, foldl_function, initial_acc, n=ALL_MESSAGES, **kwargs):
        n_int = n
        #
        partitions_int = self.storage_obj.admin.get_partitions(self.topic_str)
        #
        topic_dir_str = self.storage_obj.admin.get_topic_dir_str(self.topic_str)
        #
        config_dict = kwargs["config"] if "config" in kwargs else None
        if config_dict is not None and "auto.offset.reset" in config_dict:
            auto_offset_reset_bool = config_dict["auto.offset.reset"]
        else:
            auto_offset_reset_bool = self.storage_obj.auto_offset_reset()
        if auto_offset_reset_bool == "latest":
            partition_int_offset_tuple_dict = self.watermarks(self.topic_str, **kwargs)[self.topic_str]
            partition_int_offset_int_dict = {partition_int: offset_tuple[1] for partition_int, offset_tuple in partition_int_offset_tuple_dict.items()}
        else:
            if self.partition_int_offset_int_dict is None:
                partition_int_offset_int_dict = {partition_int: 0 for partition_int in range(partitions_int)}
            else:
                partition_int_offset_int_dict = self.partition_int_offset_int_dict
        #
        message_separator_bytes = kwargs["message_separator"] if "message_separator" in kwargs else self.storage_obj.message_separator()
        #
        partition_int_file_str_list_dict = self.storage_obj.admin.get_partition_files(self.topic_str)
        #
        partition_int_first_partition_file_str_dict = {partition_int: self.storage_obj.admin.find_partition_file_str(self.topic_str, partition_int, offset_int) for partition_int, offset_int in partition_int_offset_int_dict.items()}
        #
        partition_int_to_be_read_file_str_list_dict = {partition_int: [file_str for file_str in file_str_list if file_str >= partition_int_first_partition_file_str_dict[partition_int]] for partition_int, file_str_list in partition_int_file_str_list_dict.items()}
        #
        file_str_list_list = []
        batch_counter_int = 0
        message_counter_int = 0
        def acc_bytes_to_acc(acc, message_bytes, message_counter_int):
            serialized_message_dict = ast.literal_eval(message_bytes.decode("utf-8"))
            #
            if serialized_message_dict["offset"] >= partition_int_offset_int_dict[partition_int]:
                deserialized_message_dict = deserialize(serialized_message_dict, self.key_type_str, self.value_type_str)
                #
                acc = foldl_function(acc, deserialized_message_dict)
                #
                message_counter_int += 1
            #
            return (acc, message_counter_int)
        #

        def deserialize(message_dict, key_type, value_type):
            key_type_str = key_type
            value_type_str = value_type
            #

            def to_str(x):
                if isinstance(x, bytes):
                    return x.decode("utf-8")
                elif isinstance(x, dict):
                    return str(x)
                else:
                    return x
            #

            def to_bytes(x):
                if isinstance(x, str):
                    return x.encode("utf-8")
                elif isinstance(x, dict):
                    return str(x).encode("utf-8")
                else:
                    return x
            #

            def to_dict(x):
                if isinstance(x, bytes) or isinstance(x, str):
                    return json.loads(x)
                else:
                    return x
            #

            if key_type_str.lower() == "str":
                decode_key = to_str
            elif key_type_str.lower() == "bytes":
                decode_key = to_bytes
            elif key_type_str.lower() == "json":
                decode_key = to_dict
            #
            if value_type_str.lower() == "str":
                decode_value = to_str
            elif value_type_str.lower() == "bytes":
                decode_value = to_bytes
            elif value_type_str.lower() == "json":
                decode_value = to_dict
            #
            return_message_dict = {"headers": message_dict["headers"], "timestamp": message_dict["timestamp"], "key": decode_key(message_dict["key"]), "value": decode_value(message_dict["value"]), "offset": message_dict["offset"], "partition": message_dict["partition"]}
            return return_message_dict
        #

        for partition_int in range(partitions_int):
            file_str_list = [partition_file_str_list[batch_counter_int] for partition_file_str_list in partition_int_to_be_read_file_str_list_dict.values() if len(partition_file_str_list[partition_int]) > batch_counter_int]
            file_str_list_list.append(file_str_list)
        #

        acc = initial_acc
        for file_str_list in file_str_list_list:
            for file_str in file_str_list:
                file_bytes = self.storage_obj.admin.read_bytes_from_file(os.path.join(topic_dir_str, file_str))
                #
                message_bytes_list = file_bytes.split(message_separator_bytes)[:-1]
                for message_bytes in message_bytes_list:
                    (acc, message_counter_int) = acc_bytes_to_acc(acc, message_bytes, message_counter_int)
                    #
                    if n_int != ALL_MESSAGES:
                        if message_counter_int >= n_int:
                            return acc
        #
        return acc

    #

    def read(self, n=ALL_MESSAGES):
        def foldl_function(message_dict_list, message_dict):
            message_dict_list.append(message_dict)
            #
            return message_dict_list
        #
        return self.foldl(foldl_function, [], n)
