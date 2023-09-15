# Constants

ALL_MESSAGES = -1

#

class Pandas():
    def to_df(self, topic, n=ALL_MESSAGES, **kwargs):
        import pandas as pd
        #

        def foldl_function(acc, message_dict):
            df = pd.DataFrame.from_records([message_dict["value"]])
            #
            acc = pd.concat([acc, df], ignore_index=True)
            #
            return acc
        #

        df_n_int_tuple = self.foldl(topic, foldl_function, pd.DataFrame(), n, **kwargs)
        #
        return df_n_int_tuple

    def from_df(self, df, topic, n=ALL_MESSAGES, **kwargs):
        n_int = n
        #

        producer = self.producer(topic, **kwargs)
        for index_int, row in df.iterrows():
            if n_int != ALL_MESSAGES:
                if index_int >= n_int:
                    break
            #
            producer.produce(row.to_dict())
        producer.close()
        #
        return index_int
