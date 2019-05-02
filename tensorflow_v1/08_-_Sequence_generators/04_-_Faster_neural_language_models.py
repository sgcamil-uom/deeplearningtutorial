import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf

tf.logging.set_verbosity(tf.logging.ERROR)

max_epochs = 6000
init_stddev = 0.0001
embedding_size = 2
state_size = 2
max_seq_len = 10

tokens = [
        'i like it'.split(' '),
        'i hate it'.split(' '),
        'i don\'t hate it'.split(' '),
        'i don\'t like it'.split(' '),
    ]

sent_lens = [ len(sent) for sent in tokens ]
max_sent_len = max(sent_lens)

vocab = [ 'EDGE' ] + sorted({ token for sent in tokens for token in sent })
token2index = { token: index for (index, token) in enumerate(vocab) }
index2token = { index: token for (index, token) in enumerate(vocab) }
index_prefixes = []
index_lens = []
index_targets = []
for sent in tokens:
    sent = [ 'EDGE' ] + sent + [ 'EDGE' ]
    indexes = [ token2index[token] for token in sent ]
    indexes_len = len(indexes) - 1 #Length without one of the edges
    prefixes = indexes[:-1] + [ 0 for _ in range((max_sent_len + 1) - indexes_len) ] #Whole sentence without the right edge
    targets = indexes[1:] + [ 0 for _ in range((max_sent_len + 1) - indexes_len) ] #Whole sentence without the left edge
    
    #Dataset is set up to make the neural network predict every word in the sentence at once given the words' prefixes
    
    index_prefixes.append(prefixes)
    index_lens.append(indexes_len)
    index_targets.append(targets)

g = tf.Graph()
with g.as_default():
    prefixes = tf.placeholder(tf.int32, [None, None], 'prefixes')
    prefix_lens = tf.placeholder(tf.int32, [None], 'prefix_lens')
    targets = tf.placeholder(tf.int32, [None, None], 'targets') #Targets are now a sequence rather than a single word per prefix
    
    batch_size = tf.shape(prefixes)[0]
    seq_width = tf.shape(prefixes)[1]
    
    embedding_matrix = tf.get_variable('embedding_matrix', [len(vocab), embedding_size], tf.float32, tf.random_normal_initializer(stddev=init_stddev))
    embedded = tf.nn.embedding_lookup(embedding_matrix, prefixes)
    
    init_state = tf.get_variable('init_state', [state_size], tf.float32, tf.random_normal_initializer(stddev=init_stddev))
    batch_init = tf.tile(tf.reshape(init_state, [1, state_size]), [batch_size, 1])
    
    cell = tf.contrib.rnn.BasicRNNCell(state_size, tf.tanh)
    (outputs, _) = tf.nn.dynamic_rnn(cell, embedded, sequence_length=prefix_lens, initial_state=batch_init) #Take the outputs vectors rather than the final state only (outputs is a 3tensor)

    W = tf.get_variable('W', [state_size, len(vocab)], tf.float32, tf.random_normal_initializer(stddev=init_stddev))
    b = tf.get_variable('b', [len(vocab)], tf.float32, tf.zeros_initializer())
    outputs_2d = tf.reshape(outputs, [batch_size*seq_width, state_size]) #Cannot do a matrix multiplication on a 3tensor so reshape
    logits_2d = tf.matmul(outputs_2d, W) + b
    logits = tf.reshape(logits_2d, [batch_size, seq_width, len(vocab)]) #Reshape logits to be a 3tensor again
    probs = tf.nn.softmax(logits)
    
    next_word_probs = probs[:, -1, :] #Node that gives only the probabilities of the next word after the whole prefix (becomes a 2D matrix)

    mask = tf.sequence_mask(prefix_lens, seq_width, tf.float32) #Mask to avoid including pad words in predictions error (is a 2D matrix of 1s and 0s where 0s that corresponds to the 2D matrix of correct next word probabilities)
    error = tf.reduce_sum(tf.nn.sparse_softmax_cross_entropy_with_logits(labels=targets, logits=logits)*mask)/tf.cast(tf.reduce_sum(prefix_lens), tf.float32) #Multiply next word probabilities with mask to zero out predictions made for pad words and then find the mean of the correct predictions error (sum_error/total_words)
    
    step = tf.train.AdamOptimizer().minimize(error)

    init = tf.global_variables_initializer()

    g.finalize()

    with tf.Session() as s:
        s.run([ init ], { })

        (fig, ax) = plt.subplots(1, 1)
        plt.ion()
        
        train_errors = list()
        print('epoch', 'train error', sep='\t')
        for epoch in range(1, max_epochs+1):
            s.run([ step ], { prefixes: index_prefixes, prefix_lens: index_lens, targets: index_targets })

            [ train_error ] = s.run([ error ], { prefixes: index_prefixes, prefix_lens: index_lens, targets: index_targets })
            train_errors.append(train_error)
            
            if epoch%100 == 0:
                print(epoch, train_error, sep='\t')

                ax.cla()
                ax.plot(np.arange(len(train_errors)), train_errors, color='red', linestyle='-', label='train')
                ax.set_xlim(0, max_epochs)
                ax.set_xlabel('epoch')
                ax.set_ylim(0.0, 2.0)
                ax.set_ylabel('XE') #Cross entropy
                ax.grid(True)
                ax.set_title('Error progress')
                ax.legend()
                
                fig.tight_layout()
                plt.draw()
                plt.pause(0.0001)

        print()

        print('Sampling random sentence...')
        
        prefix_prob = 1.0
        index_prefix = [ token2index['EDGE'] ]
        for _ in range(max_seq_len):
            [ curr_probs ] = s.run([ next_word_probs ], { prefixes: [ index_prefix ], prefix_lens: [ len(index_prefix) ] }) #Use next_word_probs instead of probs when making predictions
            selected_index = np.random.choice(range(len(vocab)), p=curr_probs[0, :])
            prefix_prob = prefix_prob*curr_probs[0, selected_index]
            
            index_prefix.append(selected_index)
            
            if selected_index == token2index['EDGE']:
                break

        print('Generated sentence:', ' '.join([ index2token[i] for i in index_prefix[1:-1] ]))
        print('Sentence probability:', prefix_prob)
        
        fig.show()