from kafka import KafkaProducer, KafkaConsumer, TopicPartition
from time import sleep, time
from BankAccount import BankAccount
from datetime import datetime
from dateutil.relativedelta import relativedelta
import sys
import random
from threading import Thread


class Writter:
    """
        Encapsulate the behaviour of protocol used to control object in 
        ambient with competition (Parallel and Distributed).

        ----------
        Parameters
        ----------
        servers : [ string ]
            List of Address of server. They are fowarded to Kafka settings.

        topic : string
            Name of Topic

        id_producer : string
            Indenfier to producer module. Fowarded to Kafka.
            
        id_consumer : string
            Indenfier to consumer module. Fowarded to Kafka.
            
        partition_control : int
            Id of partition with control logs

        partition_content : int
            Id of partition with content logs
            
    """
    
    #Constructor and setting fundamentals to writter
    def __init__(self, servers, topic, id_producer, id_consumer, partition_control, partition_content ):
        #Storage of data
        self.servers = servers
        self.topic = topic
        self.id_producer = id_producer
        self.id_consumer = id_consumer
        self.partition_control = partition_control
        self.partition_content = partition_content

        
        #Connect pub
        self.producer = KafkaProducer(bootstrap_servers = servers, client_id = id_producer)

        #Specifies the partition for control and for content
        self.tp_content = [TopicPartition(topic, partition_content)]
        self.tp_control = [TopicPartition(topic, partition_control)]
        self.consumer = KafkaConsumer(bootstrap_servers=servers, auto_offset_reset= 'earliest')


    #Request access and wait until get it or die when timeout is reached
    def request(self, timeout=100):
        
        #-----REQUEST-----#
        #Request to change
        message = f"request:{self.id_producer}"
        self.producer.send(self.topic, message.encode(), partition=0)
        self.producer.flush()


        #-----WAITING-----#
        first = None                    #First element of queue
        
        time_request = time()           #Time(seconds) request
        date_request = datetime.now()   #Date of request
        valid_date = date_request-relativedelta(seconds=timeout) #Project data in reason of timeout
        #print("VALID_DATE", valid_date)
        
        while first != self.id_producer:
            #Verify timeout
            if  time() - time_request > timeout: 
                return False, "Error(Timeout)"


            #Assign consumer to partition of control
            self.consumer.assign(self.tp_control)

            #Get last position then return to first position
            self.consumer.seek_to_end(self.tp_control[0])
            sizeOffset = self.consumer.position(self.tp_control[0])
            self.consumer.seek_to_beginning(self.tp_control[0])
            
            #Get requests history
            requests_history = []   
            for message in self.consumer:
                #Verify if current event is valid
                offset_date = datetime.fromtimestamp(message.timestamp/1000.0)
                #Only consider valid requests on partition
                valid_offset = offset_date > valid_date
                
                #Store valid requests
                if valid_offset:
                    requests_history.append(message.value.decode().split(":"))

                #Break on last message
                if message.offset == sizeOffset - 1:
                    break
            
            #Get queue of pending clients then first client
            #print(requests_history)
            queue = self.get_queue(requests_history)
            #print(queue)
            if queue:
                _, first = queue[0]
            else:
                return False, "Error(Empty Queue)"


        print("QUEUE --> ", queue)
        print()
        print()
        return True, "Success(Request)"


    #Get last register of object (last event) 
    def get_content(self):
        #Assign consumer to partition of content
        self.consumer.assign(self.tp_content)
        #Get end of partition
        self.consumer.seek_to_end(self.tp_content[0])
        sizeOffset = self.consumer.position(self.tp_content[0])

        #Verify if not empty
        if sizeOffset != 0:
            #Points to last element
            self.consumer.seek(self.tp_content[0], sizeOffset-1)
            for message in self.consumer:
                #print(message.value)
                if message.offset == sizeOffset - 1:
                    break
            #Return object (encoded)
            return True, "Success(ObjectReturned)", message.value

        #If has no last content
        else:
            return False, "Error(ContentNotFinded)", None
        

    #Commit object after changes 
    def commit_content(self, message):
        self.producer.send(self.topic, message, partition=self.partition_content)
        self.producer.flush()
        return True, "Success(MenssageSended)"
    

    #Communicates the end of operations the broker
    def done(self):
        #Send done to control partition
        message = f"done:{self.id_producer}"
        self.producer.send(self.topic, message.encode(), partition=self.partition_control)
        self.producer.flush()
        return True, "Success(DoneSended)"


    #From raw control offsets get queue with pending requests 
    def get_queue(self,offset):
    
        #Verify current state of offset
        states = {}
        index = 0 
        for case, user_id in offset :
            states[user_id] = None if case == "done" else index
            index += 1
        #Store only offset on going
        offset = [ (states[key], key) for key in states.keys() if states[key] != None ]
        offset.sort(key=lambda x: x[0])

        return offset


    #Tests
    def run_tests(self):
        
        #Get Queue
        requests = [['request', 'Pub-1']]
        assert self.get_queue(requests) == [ (0, "Pub-1")]
        requests = [['done', 'Pub-1']]
        assert self.get_queue(requests) == []
        requests = [['request', 'Pub-1'], ['done', 'Pub-1']]
        assert self.get_queue(requests) == []
        requests = [['request', 'Pub-1'], ['done', 'Pub-2'], ['request', 'Pub-2']]
        assert self.get_queue(requests) == [ (0, "Pub-1"), (2, "Pub-2") ]
        requests = [['request', 'Pub-1'], ['done', 'Pub-2'], ['request', 'Pub-2'], ['done', 'Pub-1'], ['request', 'Pub-3']]
        assert self.get_queue(requests) == [ (2, "Pub-2"), (4, "Pub-3") ]
        requests = [['request', 'Pub-1'], ['done', 'Pub-2'], ['request', 'Pub-2'], ['done', 'Pub-1'], ['request', 'Pub-3'], ['request', 'Pub-1']]
        assert self.get_queue(requests) == [ (2, "Pub-2"), (4, "Pub-3"), (5, 'Pub-1') ]

        return True, "Success(Tests) !"


    #Formated print
    def print(self):
        print("Print Writter {")
        print( "\tservers:", self.servers)
        print( "\ttopic:", self.topic)
        print( "\tid_producer:", self.id_producer)
        print( "\tid_consumer:", self.id_consumer)
        print( "\tpartition_control:", self.partition_control)
        print( "\tpartition_content:", self.partition_content)
        print("}")
        

def routine(prefix_name, sufix_name, repeats, timeout, servers, topic, partition_control, partition_content ):

    for _ in range(repeats):
        #print("-------CREATE-CONNECTION------")
        w1 = Writter(servers, topic, f"{prefix_name + sufix_name}", f"{prefix_name + sufix_name}", partition_control, partition_content)
        #w1.print()

        #print("-------REQUESTING-OBJECT-------")
        success, msg = w1.request(timeout=timeout)
        #print(msg)
        if not success:
            sys.exit()
        
        #print("-------CHANGING-OBJECT-------")
        success, msg, obj = w1.get_content()
        #print(msg)

        #If the object not exists
        if not success and msg == "Error(ContentNotFinded)":
            account = BankAccount(holder=prefix_name, checking_balance=100.0, savings_balance=800.0)
            obj = account.toJson().encode()
        elif not success:
            sys.exit()
        
        #Decode Object
        obj_json = obj.decode()
        account = BankAccount(json=obj_json)

        #Deposit or Withdraw  on account
        #print(f"Checking Balance: {account.checking_balance} -> ", end="")
        random_value = random.randint(-10,10)
        #print(f"{account.checking_balance} + {random_value} -> ", end="")
        account.checking_balance = account.checking_balance + random_value 
        #print(f"{account.checking_balance}")
        #Encode Object
        obj = account.toJson().encode()

        #print("-------COMMITING-OBJECT-------")
        success, msg = w1.commit_content(obj)
        #print(msg)
        if not success:
            sys.exit()

        #print("-------RELEADING-OBJECT-------")
        success, msg = w1.done()
        #print(msg)
        if not success:
            sys.exit()



if __name__ == "__main__":

  

    
    server = ['localhost:19092']
    topic = "Teste"
    prefix_name = "Pub-"
    partition_control = 0
    partition_content = 1  
    repeats = 10
    num_threads = 10
    timeout=50

    #Read arguments
    num_threads = int(sys.argv[1])
    repeats = int(sys.argv[2])
    timeour = sys.argv[3]
    prefix_name = sys.argv[4]
    topic = sys.argv[5]
    serverIP = sys.argv[6]
    serverPort = sys.argv[7]
    server = serverIP + ":" + serverPort
    partition_control = int(sys.argv[8])
    partition_content = int(sys.argv[9])


    for i in range(num_threads):
        Thread(target= routine, args=(prefix_name, f"{i+1}", repeats, timeout,  server, topic, partition_control, partition_content, )).start()
        sleep(5)
