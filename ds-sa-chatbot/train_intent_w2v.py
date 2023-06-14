#w2v를 활용하여 재구성한 의도 모델링입니다. w2v에 맞추어 파라미터도 재구성되어있습니다.

from train_tools.qna import create_train_data_table
from train_tools.qna import load_train_data
from train_tools.dict import create_dict

# 필요한 모듈 임포트
import pandas as pd
import tensorflow as tf
import numpy as np
import gensim
from tensorflow.keras import preprocessing
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Embedding, Dense, Dropout, Conv1D, GlobalMaxPool1D, concatenate
import os

# 데이터 읽어오기
train_file = "total_train_data.csv"
data = pd.read_csv('models/intent/'+train_file, delimiter=',')
queries = data['query'].tolist()
intents = data['intent'].tolist()


from utils.PreprocessW2V import PreprocessW2V as Preprocess
p = Preprocess(userdic='utils/user_dic.tsv')

# 단어 시퀀스 생성
sequences = []
for sentence in queries:
    pos = p.pos(sentence)
    keywords = p.get_keywords(pos, without_tag=True)
    seq = p.get_wordidx_sequence(keywords)
    sequences.append(seq)


# 단어 인덱스 시퀀스 벡터 ○2
# 단어 시퀀스 벡터 크기
from config.GlobalParams import MAX_SEQ_LEN
padded_seqs = preprocessing.sequence.pad_sequences(sequences, maxlen=MAX_SEQ_LEN, padding='post')

# (105658, 15)
print(padded_seqs.shape)
print(len(intents)) #105658

# 학습용, 검증용, 테스트용 데이터셋 생성 ○3
# 학습셋:검증셋:테스트셋 = 7:2:1
ds = tf.data.Dataset.from_tensor_slices((padded_seqs, intents))
ds = ds.shuffle(len(queries))

train_size = int(len(padded_seqs) * 0.7)
val_size = int(len(padded_seqs) * 0.2)
test_size = int(len(padded_seqs) * 0.1)

train_ds = ds.take(train_size).batch(20)
val_ds = ds.skip(train_size).take(val_size).batch(20)
test_ds = ds.skip(train_size + val_size).take(test_size).batch(20)

# 하이퍼 파라미터 설정
dropout_prob = 0.5
EMB_SIZE = 200 #ko.kv의 사이즈에 맞춰 사이즈 변경
EPOCH = 5
VOCAB_SIZE = len(p.word_index) + 1 #전체 단어 개수

#####Added Code#######
kv = gensim.models.Word2Vec.load('ko_with_corpus_mc1_menu_added.model')

## setting Embeddings
embeddings = np.zeros((VOCAB_SIZE, EMB_SIZE))
for word,idx in p.word_index.items():
    ## update the row with vector
    try:
        embeddings[idx] =  kv.wv[word] #Embedding Layer를 w2v에 맞추어 재구성
    ## if word not in model then skip and the row stays all 0s
    except:
        pass
######################

# CNN 모델 정의  ○4
input_layer = Input(shape=(MAX_SEQ_LEN,))
#embedding_layer = Embedding(VOCAB_SIZE, EMB_SIZE, input_length=MAX_SEQ_LEN)(input_layer)
#Embedding Layer를 w2v에 맞추어 재구성
embedding_layer = Embedding(VOCAB_SIZE, EMB_SIZE, weights=[embeddings], input_length=MAX_SEQ_LEN)(input_layer) 

dropout_emb = Dropout(rate=dropout_prob)(embedding_layer)

conv1 = Conv1D(
    filters=200,
    kernel_size=3,
    padding='valid',
    activation=tf.nn.relu)(dropout_emb)
pool1 = GlobalMaxPool1D()(conv1)

conv2 = Conv1D(
    filters=200,
    kernel_size=4,
    padding='valid',
    activation=tf.nn.relu)(dropout_emb)
pool2 = GlobalMaxPool1D()(conv2)

conv3 = Conv1D(
    filters=200,
    kernel_size=5,
    padding='valid',
    activation=tf.nn.relu)(dropout_emb)
pool3 = GlobalMaxPool1D()(conv3)

# 3,4,5gram 이후 합치기
concat = concatenate([pool1, pool2, pool3])

hidden = Dense(200, activation=tf.nn.relu)(concat)
dropout_hidden = Dropout(rate=dropout_prob)(hidden)
logits = Dense(5, name='logits')(dropout_hidden)
predictions = Dense(5, activation=tf.nn.softmax)(logits)


# 모델 생성  ○5
model = Model(inputs=input_layer, outputs=predictions)
model.compile(optimizer='adam',
              loss='sparse_categorical_crossentropy',
              metrics=['accuracy'])


# 모델 학습 ○6
model.fit(train_ds, validation_data=val_ds, epochs=EPOCH, verbose=1)


# 모델 평가(테스트 데이터 셋 이용) ○7
loss, accuracy = model.evaluate(test_ds, verbose=1)
print('Accuracy: %f' % (accuracy * 100))
print('loss: %f' % (loss))


# 모델 저장  ○8
model.save('./models/intent/intent_w2v_model.h5')