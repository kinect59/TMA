import logging
import os

import numpy as np

from keras import backend as K
from keras.layers import *
from keras.models import model_from_json, Model
from keras.regularizers import l2
from keras_wrapper.cnn_model import Model_Wrapper
from keras_wrapper.extra.regularize import Regularize


class VideoDesc_Model(Model_Wrapper):
    """
    Translation model class. Instance of the Model_Wrapper class (see staged_keras_wrapper).
    """

    def resumeTrainNet(self, ds, params, out_name=None):
        pass

    def __init__(self, params, type='VideoDesc_Model', verbose=1, structure_path=None, weights_path=None,
                 model_name=None, vocabularies=None, store_path=None, set_optimizer=True, clear_dirs=True):
        """
            VideoDesc_Model object constructor.

            :param params: all hyperparameters of the model.
            :param type: network name type (corresponds to any method defined in the section 'MODELS' of this class). Only valid if 'structure_path' == None.
            :param verbose: set to 0 if you don't want the model to output informative messages
            :param structure_path: path to a Keras' model json file. If we speficy this parameter then 'type' will be only an informative parameter.
            :param weights_path: path to the pre-trained weights file (if None, then it will be randomly initialized)
            :param model_name: optional name given to the network (if None, then it will be assigned to current time as its name)
            :param vocabularies: vocabularies used for GLOVE word embedding
            :param store_path: path to the folder where the temporal model packups will be stored

            References:
                [PReLU]
                Kaiming He et al. Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification

                [BatchNormalization]
                Sergey Ioffe and Christian Szegedy. Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift
        """
        super(self.__class__, self).__init__(type=type, model_name=model_name,
                                             silence=verbose == 0, models_path=store_path, inheritance=True)

        self.__toprint = ['_model_type', 'name', 'model_path', 'verbose']

        self.verbose = verbose
        self._model_type = type
        self.params = params
        self.vocabularies = vocabularies
        self.ids_inputs = params['INPUTS_IDS_MODEL']
        self.ids_outputs = params['OUTPUTS_IDS_MODEL']
        # Sets the model name and prepares the folders for storing the models
        self.setName(model_name, models_path=store_path, clear_dirs=clear_dirs)

        # Prepare target word embedding
        if params['TRG_PRETRAINED_VECTORS'] is not None:
            if self.verbose > 0:
                logging.info("<<< Loading pretrained word vectors from: " + params['TRG_PRETRAINED_VECTORS'] + " >>>")
            self.trg_word_vectors = np.load(os.path.join(params['TRG_PRETRAINED_VECTORS'])).item()
            self.trg_embedding_weights = np.random.rand(params['OUTPUT_VOCABULARY_SIZE'],
                                                        params['TARGET_TEXT_EMBEDDING_SIZE'])
            for word, index in self.vocabularies[self.ids_outputs[0]]['words2idx'].iteritems():
                if self.trg_word_vectors.get(word) is not None:
                    self.trg_embedding_weights[index, :] = self.trg_word_vectors[word]
            self.trg_embedding_weights = [self.trg_embedding_weights]
            self.trg_embedding_weights_trainable = params['TRG_PRETRAINED_VECTORS_TRAINABLE']
            del self.trg_word_vectors
        else:
            self.trg_embedding_weights = None
            self.trg_embedding_weights_trainable = True

        # Prepare model
        if structure_path:
            # Load a .json model
            if self.verbose > 0:
                logging.info("<<< Loading model structure from file " + structure_path + " >>>")
            self.model = model_from_json(open(structure_path).read())
        else:
            # Build model from scratch
            if hasattr(self, type):
                if self.verbose > 0:
                    logging.info("<<< Building '" + type + "' Video Captioning Model >>>")
                eval('self.' + type + '(params)')
            else:
                raise Exception('Video_Captioning_Model type "' + type + '" is not implemented.')

        # Load weights from file
        if weights_path:
            if self.verbose > 0:
                logging.info("<<< Loading weights from file " + weights_path + " >>>")
            self.model.load_weights(weights_path)

        # Print information of self
        if verbose > 0:
            print str(self)
            self.model.summary()
        if set_optimizer:
            self.setOptimizer()

    def setOptimizer(self, **kwargs):

        """
        Sets a new optimizer for the Translation_Model.
        :param **kwargs:
        """

        super(self.__class__, self).setOptimizer(lr=self.params['LR'],
                                                 clipnorm=self.params['CLIP_C'],
                                                 loss=self.params['LOSS'],
                                                 optimizer=self.params['OPTIMIZER'],
                                                 sample_weight_mode='temporal' if self.params.get('SAMPLE_WEIGHTS',
                                                                                                  False) else None)

    def __str__(self):
        """
        Plots basic model information.
        """
        obj_str = '-----------------------------------------------------------------------------------\n'
        class_name = self.__class__.__name__
        obj_str += '\t\t' + class_name + ' instance\n'
        obj_str += '-----------------------------------------------------------------------------------\n'

        # Print pickled attributes
        for att in self.__toprint:
            obj_str += att + ': ' + str(self.__dict__[att])
            obj_str += '\n'

        obj_str += '\n'
        obj_str += 'MODEL params:\n'
        obj_str += str(self.params)
        obj_str += '\n'
        obj_str += '-----------------------------------------------------------------------------------'

        return obj_str

    # ------------------------------------------------------- #
    #       PREDEFINED MODELS
    # ------------------------------------------------------- #

    def DeepSeek(self, params):
        """
        :param params:
        :return:
        """

        # Video model
        video = Input(name=self.ids_inputs[0], shape=tuple([None, params['IMG_FEAT_SIZE']]))
        input_video = video
        ##################################################################
        #                       ENCODER
        ##################################################################

        encoder = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                         W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         return_sequences=True),
                                name='bidirectional_encoder_' + params['RNN_TYPE'],
                                merge_mode='concat')(input_video)
        input_video = Regularize(encoder, params, name='after_blstm1')

        # Affine layer (not their best model)
        """
        encoder_back = TimeDistributed(Dense(params['AFFINE_LAYERS_DIM'])
                                       , name='affine_back')(encoder_back)
        encoder = TimeDistributed(Dense(params['AFFINE_LAYERS_DIM'])
                                  , name='affine_forw')(encoder)
        input_video = Lambda(function=lambda x: K.sum(x, axis=1),
                             output_shape=lambda shape: shape[0],
                             mask_function=lambda x, m: m[0])([encoder_back, encoder])
        input_video = TimeDistributed(Activation('relu'))(input_video)
        """

        # They alternatively use a double BLSTM encoder
        input_video = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                             W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                             U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                             b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                             dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                 'USE_RECURRENT_DROPOUT'] else None,
                                                             dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                 'USE_RECURRENT_DROPOUT'] else None,
                                                             return_sequences=True),
                                    name='bidirectional_encoder2_' + params['RNN_TYPE'],
                                    merge_mode='concat')(input_video)
        input_video = Regularize(input_video, params, name='after_blstm2')

        # Previously generated words as inputs for training
        next_words = Input(name=self.ids_inputs[1], batch_shape=tuple([None, None]), dtype='int32')
        emb = Embedding(params['OUTPUT_VOCABULARY_SIZE'],
                        params['TARGET_TEXT_EMBEDDING_SIZE'],
                        name='target_word_embedding',
                        W_regularizer=l2(params['WEIGHT_DECAY']),
                        trainable=self.trg_embedding_weights_trainable,
                        weights=self.trg_embedding_weights,
                        mask_zero=True)(next_words)
        emb = Regularize(emb, params, name='target_word_embedding')

        # LSTM initialization perceptrons with ctx mean
        # 3.2. Decoder's RNN initialization perceptrons with ctx mean
        ctx_mean = Lambda(lambda x: K.mean(x, axis=1),
                          output_shape=lambda s: (s[0], s[2]), name='lambda_mean')(input_video)

        if len(params['INIT_LAYERS']) > 0:
            for n_layer_init in range(len(params['INIT_LAYERS']) - 1):
                ctx_mean = Dense(params['DECODER_HIDDEN_SIZE'], name='init_layer_%d' % n_layer_init,
                                 W_regularizer=l2(params['WEIGHT_DECAY']),
                                 activation=params['INIT_LAYERS'][n_layer_init]
                                 )(ctx_mean)
                ctx_mean = Regularize(ctx_mean, params, name='ctx' + str(n_layer_init))

            initial_state = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_state',
                                  W_regularizer=l2(params['WEIGHT_DECAY']),
                                  activation=params['INIT_LAYERS'][-1]
                                  )(ctx_mean)
            initial_state = Regularize(initial_state, params, name='initial_state')
            input_attentional_decoder = [emb, input_video, initial_state]

            if params['RNN_TYPE'] == 'LSTM':
                initial_memory = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_memory',
                                       W_regularizer=l2(params['WEIGHT_DECAY']),
                                       activation=params['INIT_LAYERS'][-1])(ctx_mean)
                initial_memory = Regularize(initial_memory, params, name='initial_memory')
                input_attentional_decoder.append(initial_memory)
        else:
            input_attentional_decoder = [emb, input_video]

        ##################################################################
        #                       DECODER
        ##################################################################

        # 3.3. LSTM decoder
        sharedRNN = eval(params['RNN_TYPE'] + 'Cond')(params['DECODER_HIDDEN_SIZE'],
                                                      W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                      U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                      b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                      dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                          'USE_RECURRENT_DROPOUT'] else None,
                                                      dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                          'USE_RECURRENT_DROPOUT'] else None,
                                                      return_sequences=True,
                                                      name='decoder_' + params['RNN_TYPE'] + 'Cond')

        proj_h = sharedRNN(input_attentional_decoder)

        # 3.7. Output layer: Softmax
        shared_FC_soft = TimeDistributed(Dense(params['OUTPUT_VOCABULARY_SIZE'],
                                               activation=params['CLASSIFIER_ACTIVATION'],
                                               W_regularizer=l2(params['WEIGHT_DECAY']),
                                               name=params['CLASSIFIER_ACTIVATION']
                                               ),
                                         name=self.ids_outputs[0])
        softout = shared_FC_soft(proj_h)

        self.model = Model(input=[video, next_words], output=softout)

    def ArcticVideoCaptionWithInit(self, params):
        """
        Video captioning with:
            * Attention mechansim on video frames
            * Conditional LSTM for processing the video
            * Feed forward layers:
                + Context projected to output
                + Last word projected to output
        :param params:
        :return:
        """

        # Video model
        # video = Input(name=self.ids_inputs[0], shape=tuple([params['NUM_FRAMES'], params['IMG_FEAT_SIZE']]))
        video = Input(name=self.ids_inputs[0], shape=tuple([None, params['IMG_FEAT_SIZE']]))
        input_video = video
        ##################################################################
        #                       ENCODER
        ##################################################################
        for activation, dimension in params['IMG_EMBEDDING_LAYERS']:
            input_video = TimeDistributed(Dense(dimension, name='%s_1' % activation, activation=activation,
                                                W_regularizer=l2(params['WEIGHT_DECAY'])))(input_video)
            input_video = Regularize(input_video, params, name='%s_1' % activation)

        if params['ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_ENCODER']:
                encoder = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                 W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                 dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                 return_sequences=True),
                                        name='bidirectional_encoder_' + params['RNN_TYPE'],
                                        merge_mode='concat')(input_video)
            else:
                encoder = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                   W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                   dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                   return_sequences=True,
                                                   name='encoder_' + params['RNN_TYPE'])(input_video)
            input_video = merge([input_video, encoder], mode='concat', concat_axis=2)
            input_video = Regularize(input_video, params, name='input_video')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_ENCODER']:
                    current_input_video = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                                 W_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 U_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 b_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 dropout_W=params[
                                                                                     'RECURRENT_DROPOUT_P'] if params[
                                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                                 dropout_U=params[
                                                                                     'RECURRENT_DROPOUT_P'] if params[
                                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                                 return_sequences=True,
                                                                                 ),
                                                        merge_mode='concat',
                                                        name='bidirectional_encoder_' + str(n_layer))(input_video)
                else:
                    current_input_video = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                   W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                   dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                   return_sequences=True,
                                                                   name='encoder_' + str(n_layer))(input_video)

                current_input_video = Regularize(current_input_video, params, name='input_video_' + str(n_layer))
                input_video = merge([input_video, current_input_video], mode='sum')

        # Previously generated words as inputs for training
        next_words = Input(name=self.ids_inputs[1], batch_shape=tuple([None, None]), dtype='int32')
        emb = Embedding(params['OUTPUT_VOCABULARY_SIZE'],
                        params['TARGET_TEXT_EMBEDDING_SIZE'],
                        name='target_word_embedding',
                        W_regularizer=l2(params['WEIGHT_DECAY']),
                        trainable=self.trg_embedding_weights_trainable,
                        weights=self.trg_embedding_weights,
                        mask_zero=True)(next_words)
        emb = Regularize(emb, params, name='target_word_embedding')

        # LSTM initialization perceptrons with ctx mean
        # 3.2. Decoder's RNN initialization perceptrons with ctx mean
        ctx_mean = Lambda(lambda x: K.mean(x, axis=1),
                          output_shape=lambda s: (s[0], s[2]), name='lambda_mean')(input_video)

        if len(params['INIT_LAYERS']) > 0:
            for n_layer_init in range(len(params['INIT_LAYERS']) - 1):
                ctx_mean = Dense(params['DECODER_HIDDEN_SIZE'], name='init_layer_%d' % n_layer_init,
                                 W_regularizer=l2(params['WEIGHT_DECAY']),
                                 activation=params['INIT_LAYERS'][n_layer_init]
                                 )(ctx_mean)
                ctx_mean = Regularize(ctx_mean, params, name='ctx' + str(n_layer_init))

            initial_state = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_state',
                                  W_regularizer=l2(params['WEIGHT_DECAY']),
                                  activation=params['INIT_LAYERS'][-1]
                                  )(ctx_mean)
            initial_state = Regularize(initial_state, params, name='initial_state')
            input_attentional_decoder = [emb, input_video, initial_state]

            if params['RNN_TYPE'] == 'LSTM':
                initial_memory = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_memory',
                                       W_regularizer=l2(params['WEIGHT_DECAY']),
                                       activation=params['INIT_LAYERS'][-1])(ctx_mean)
                initial_memory = Regularize(initial_memory, params, name='initial_memory')
                input_attentional_decoder.append(initial_memory)
        else:
            input_attentional_decoder = [emb, input_video]
        ##################################################################
        #                       DECODER
        ##################################################################

        # 3.3. Attentional decoder
        sharedAttRNNCond = eval('Att' + params['RNN_TYPE'] + 'Cond')(params['DECODER_HIDDEN_SIZE'],
                                                                     W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     V_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                     Wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                     Ua_regularizer=l2(params['WEIGHT_DECAY']),
                                                                     ba_regularizer=l2(params['WEIGHT_DECAY']),
                                                                     dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_V=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_wa=params['DROPOUT_P'] if params[
                                                                         'USE_DROPOUT'] else None,
                                                                     dropout_Wa=params['DROPOUT_P'] if params[
                                                                         'USE_DROPOUT'] else None,
                                                                     dropout_Ua=params['DROPOUT_P'] if params[
                                                                         'USE_DROPOUT'] else None,
                                                                     return_sequences=True,
                                                                     return_extra_variables=True,
                                                                     return_states=True,
                                                                     name='decoder_Att' + params['RNN_TYPE'] + 'Cond')

        rnn_output = sharedAttRNNCond(input_attentional_decoder)
        proj_h = rnn_output[0]
        x_att = rnn_output[1]
        alphas = rnn_output[2]
        h_state = rnn_output[3]
        if params['RNN_TYPE'] == 'LSTM':
            h_memory = rnn_output[4]

        [proj_h, shared_reg_proj_h] = Regularize(proj_h, params, shared_layers=True, name='proj_h0')

        shared_FC_mlp = TimeDistributed(Dense(params['SKIP_VECTORS_HIDDEN_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_lstm')
        out_layer_mlp = shared_FC_mlp(proj_h)
        shared_FC_ctx = TimeDistributed(Dense(params['SKIP_VECTORS_HIDDEN_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_ctx')
        out_layer_ctx = shared_FC_ctx(x_att)

        shared_Lambda_Permute = PermuteGeneral((1, 0, 2))
        out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
        shared_FC_emb = TimeDistributed(Dense(params['SKIP_VECTORS_HIDDEN_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear'),
                                        name='logit_emb')
        out_layer_emb = shared_FC_emb(emb)

        [out_layer_mlp, shared_reg_out_layer_mlp] = Regularize(out_layer_mlp, params,
                                                               shared_layers=True, name='out_layer_mlp')
        [out_layer_ctx, shared_reg_out_layer_ctx] = Regularize(out_layer_ctx, params,
                                                               shared_layers=True, name='out_layer_ctx')
        [out_layer_emb, shared_reg_out_layer_emb] = Regularize(out_layer_emb, params,
                                                               shared_layers=True, name='out_layer_emb')

        additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb],
                                  mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='additional_input')
        shared_activation_tanh = Activation('tanh')

        out_layer = shared_activation_tanh(additional_output)

        shared_deep_list = []
        shared_reg_deep_list = []
        # 3.6 Optional deep ouput layer
        for i, (activation, dimension) in enumerate(params['DEEP_OUTPUT_LAYERS']):
            if activation.lower() == 'maxout':
                shared_deep_list.append(TimeDistributed(MaxoutDense(dimension,
                                                                    W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name='maxout_%d' % i))
            else:
                shared_deep_list.append(TimeDistributed(Dense(dimension, activation=activation,
                                                              W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name=activation + '_%d' % i))
            out_layer = shared_deep_list[-1](out_layer)
            [out_layer, shared_reg_out_layer] = Regularize(out_layer,
                                                           params, shared_layers=True,
                                                           name='out_layer' + str(activation))
            shared_reg_deep_list.append(shared_reg_out_layer)

        # 3.7. Output layer: Softmax
        shared_FC_soft = TimeDistributed(Dense(params['OUTPUT_VOCABULARY_SIZE'],
                                               activation=params['CLASSIFIER_ACTIVATION'],
                                               W_regularizer=l2(params['WEIGHT_DECAY']),
                                               name=params['CLASSIFIER_ACTIVATION']
                                               ),
                                         name=self.ids_outputs[0])
        softout = shared_FC_soft(out_layer)

        self.model = Model(input=[video, next_words], output=softout)

        ##################################################################
        #               BEAM SEARCH OPTIMIZED MODEL                      #
        ##################################################################
        # Now that we have the basic training model ready, let's prepare the model for applying decoding
        # The beam-search model will include all the minimum required set of layers (decoder stage) which offer the
        # possibility to generate the next state in the sequence given a pre-processed input (encoder stage)
        if params['BEAM_SEARCH']:
            # First, we need a model that outputs the preprocessed input + initial h state
            # for applying the initial forward pass
            model_init_input = [video, next_words]
            model_init_output = [softout, input_video, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_init_output.append(h_memory)

            self.model_init = Model(input=model_init_input, output=model_init_output)

            # Store inputs and outputs names for model_init
            self.ids_inputs_init = self.ids_inputs
            # first output must be the output probs.
            self.ids_outputs_init = self.ids_outputs + ['preprocessed_input', 'next_state']
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_outputs_init.append('next_memory')

            # Second, we need to build an additional model with the capability to have the following inputs:
            #   - preprocessed_input
            #   - prev_word
            #   - prev_state
            # and the following outputs:
            #   - softmax probabilities
            #   - next_state
            if params['ENCODER_HIDDEN_SIZE'] > 0:
                if params['BIDIRECTIONAL_ENCODER']:
                    preprocessed_size = params['ENCODER_HIDDEN_SIZE'] * 2 + params['IMG_FEAT_SIZE']
                else:
                    preprocessed_size = params['ENCODER_HIDDEN_SIZE'] + params['IMG_FEAT_SIZE']
            else:
                preprocessed_size = params['IMG_FEAT_SIZE']

            # Define inputs
            preprocessed_annotations = Input(name='preprocessed_input',
                                             shape=tuple([params['NUM_FRAMES'], preprocessed_size]))
            prev_h_state = Input(name='prev_state', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
            input_attentional_decoder = [emb, preprocessed_annotations, prev_h_state]

            if params['RNN_TYPE'] == 'LSTM':
                prev_h_memory = Input(name='prev_memory', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
                input_attentional_decoder.append(prev_h_memory)
            # Apply decoder
            rnn_output = sharedAttRNNCond(input_attentional_decoder)
            proj_h = rnn_output[0]
            x_att = rnn_output[1]
            alphas = rnn_output[2]
            h_state = rnn_output[3]
            if params['RNN_TYPE'] == 'LSTM':
                h_memory = rnn_output[4]
            for reg in shared_reg_proj_h:
                proj_h = reg(proj_h)

            out_layer_mlp = shared_FC_mlp(proj_h)
            out_layer_ctx = shared_FC_ctx(x_att)
            out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
            out_layer_emb = shared_FC_emb(emb)

            for (reg_out_layer_mlp, reg_out_layer_ctx, reg_out_layer_emb) in zip(shared_reg_out_layer_mlp,
                                                                                 shared_reg_out_layer_ctx,
                                                                                 shared_reg_out_layer_emb):
                out_layer_mlp = reg_out_layer_mlp(out_layer_mlp)
                out_layer_ctx = reg_out_layer_ctx(out_layer_ctx)
                out_layer_emb = reg_out_layer_emb(out_layer_emb)

            additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb],
                                      mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='additional_input_model_next')
            out_layer = shared_activation_tanh(additional_output)

            for (deep_out_layer, reg_list) in zip(shared_deep_list, shared_reg_deep_list):
                out_layer = deep_out_layer(out_layer)
                for reg in reg_list:
                    out_layer = reg(out_layer)

            # Softmax
            softout = shared_FC_soft(out_layer)
            model_next_inputs = [next_words, preprocessed_annotations, prev_h_state]
            model_next_outputs = [softout, preprocessed_annotations, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_next_inputs.append(prev_h_memory)
                model_next_outputs.append(h_memory)

            self.model_next = Model(input=model_next_inputs,
                                    output=model_next_outputs)

            # Store inputs and outputs names for model_next
            # first input must be previous word
            self.ids_inputs_next = [self.ids_inputs[1]] + ['preprocessed_input', 'prev_state']
            # first output must be the output probs.
            self.ids_outputs_next = self.ids_outputs + ['preprocessed_input', 'next_state']

            # Input -> Output matchings from model_init to model_next and from model_next to model_next
            self.matchings_init_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'next_state': 'prev_state'}
            self.matchings_next_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'next_state': 'prev_state'}
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_inputs_next.append('prev_memory')
                self.ids_outputs_next.append('next_memory')
                self.matchings_init_to_next['next_memory'] = 'prev_memory'
                self.matchings_next_to_next['next_memory'] = 'prev_memory'

    def ArcticVideoCaptionNoLSTMEncWithInit(self, params):
        """
        Video captioning with:
            * Attention mechansim on video frames
            * Conditional LSTM for processing the video
            * Feed forward layers:
                + Context projected to output
                + Last word projected to output
        :param params:
        :return:
        """

        # Video model
        # video = Input(name=self.ids_inputs[0], shape=tuple([params['NUM_FRAMES'], params['IMG_FEAT_SIZE']]))
        video = Input(name=self.ids_inputs[0], shape=tuple([None, params['IMG_FEAT_SIZE']]))
        input_video = video
        ##################################################################
        #                       ENCODER
        ##################################################################
        for activation, dimension in params['IMG_EMBEDDING_LAYERS']:
            input_video = TimeDistributed(Dense(dimension, name='%s_1' % activation, activation=activation,
                                                W_regularizer=l2(params['WEIGHT_DECAY'])))(input_video)
            input_video = Regularize(input_video, params, name='%s_1' % activation)

        input_video = Regularize(input_video, params, name='input_video')

        # Previously generated words as inputs for training
        next_words = Input(name=self.ids_inputs[1], batch_shape=tuple([None, None]), dtype='int32')
        emb = Embedding(params['OUTPUT_VOCABULARY_SIZE'],
                        params['TARGET_TEXT_EMBEDDING_SIZE'],
                        name='target_word_embedding',
                        W_regularizer=l2(params['WEIGHT_DECAY']),
                        trainable=self.trg_embedding_weights_trainable,
                        weights=self.trg_embedding_weights,
                        mask_zero=True)(next_words)
        emb = Regularize(emb, params, name='target_word_embedding')

        # LSTM initialization perceptrons with ctx mean
        # 3.2. Decoder's RNN initialization perceptrons with ctx mean
        ctx_mean = Lambda(lambda x: K.mean(x, axis=1),
                          output_shape=lambda s: (s[0], s[2]), name='lambda_mean')(input_video)

        if len(params['INIT_LAYERS']) > 0:
            for n_layer_init in range(len(params['INIT_LAYERS']) - 1):
                ctx_mean = Dense(params['DECODER_HIDDEN_SIZE'], name='init_layer_%d' % n_layer_init,
                                 W_regularizer=l2(params['WEIGHT_DECAY']),
                                 activation=params['INIT_LAYERS'][n_layer_init]
                                 )(ctx_mean)
                ctx_mean = Regularize(ctx_mean, params, name='ctx' + str(n_layer_init))

            initial_state = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_state',
                                  W_regularizer=l2(params['WEIGHT_DECAY']),
                                  activation=params['INIT_LAYERS'][-1]
                                  )(ctx_mean)
            initial_state = Regularize(initial_state, params, name='initial_state')
            input_attentional_decoder = [emb, input_video, initial_state]

            if params['RNN_TYPE'] == 'LSTM':
                initial_memory = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_memory',
                                       W_regularizer=l2(params['WEIGHT_DECAY']),
                                       activation=params['INIT_LAYERS'][-1])(ctx_mean)
                initial_memory = Regularize(initial_memory, params, name='initial_memory')
                input_attentional_decoder.append(initial_memory)
        else:
            input_attentional_decoder = [emb, input_video]
        ##################################################################
        #                       DECODER
        ##################################################################

        # 3.3. Attentional decoder
        sharedAttRNNCond = eval('Att' + params['RNN_TYPE'] + 'Cond')(params['DECODER_HIDDEN_SIZE'],
                                                                     W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     V_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                     Wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                     Ua_regularizer=l2(params['WEIGHT_DECAY']),
                                                                     ba_regularizer=l2(params['WEIGHT_DECAY']),
                                                                     dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_V=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_wa=params['DROPOUT_P'] if params[
                                                                         'USE_DROPOUT'] else None,
                                                                     dropout_Wa=params['DROPOUT_P'] if params[
                                                                         'USE_DROPOUT'] else None,
                                                                     dropout_Ua=params['DROPOUT_P'] if params[
                                                                         'USE_DROPOUT'] else None,
                                                                     return_sequences=True,
                                                                     return_extra_variables=True,
                                                                     return_states=True,
                                                                     name='decoder_Att' + params['RNN_TYPE'] + 'Cond')

        rnn_output = sharedAttRNNCond(input_attentional_decoder)
        proj_h = rnn_output[0]
        x_att = rnn_output[1]
        alphas = rnn_output[2]
        h_state = rnn_output[3]
        if params['RNN_TYPE'] == 'LSTM':
            h_memory = rnn_output[4]

        [proj_h, shared_reg_proj_h] = Regularize(proj_h, params, shared_layers=True, name='proj_h0')

        shared_FC_mlp = TimeDistributed(Dense(params['DECODER_HIDDEN_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_lstm')
        out_layer_mlp = shared_FC_mlp(proj_h)
        shared_FC_ctx = TimeDistributed(Dense(params['DECODER_HIDDEN_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_ctx')
        out_layer_ctx = shared_FC_ctx(x_att)

        shared_Lambda_Permute = PermuteGeneral((1, 0, 2))
        out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
        shared_FC_emb = TimeDistributed(Dense(params['DECODER_HIDDEN_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear'),
                                        name='logit_emb')
        out_layer_emb = shared_FC_emb(emb)

        [out_layer_mlp, shared_reg_out_layer_mlp] = Regularize(out_layer_mlp, params,
                                                               shared_layers=True, name='out_layer_mlp')
        [out_layer_ctx, shared_reg_out_layer_ctx] = Regularize(out_layer_ctx, params,
                                                               shared_layers=True, name='out_layer_ctx')
        [out_layer_emb, shared_reg_out_layer_emb] = Regularize(out_layer_emb, params,
                                                               shared_layers=True, name='out_layer_emb')

        additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb],
                                  mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='additional_input')
        shared_activation_tanh = Activation('tanh')

        out_layer = shared_activation_tanh(additional_output)

        shared_deep_list = []
        shared_reg_deep_list = []
        # 3.6 Optional deep ouput layer
        for i, (activation, dimension) in enumerate(params['DEEP_OUTPUT_LAYERS']):
            if activation.lower() == 'maxout':
                shared_deep_list.append(TimeDistributed(MaxoutDense(dimension,
                                                                    W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name='maxout_%d' % i))
            else:
                shared_deep_list.append(TimeDistributed(Dense(dimension, activation=activation,
                                                              W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name=activation + '_%d' % i))
            out_layer = shared_deep_list[-1](out_layer)
            [out_layer, shared_reg_out_layer] = Regularize(out_layer,
                                                           params, shared_layers=True,
                                                           name='out_layer' + str(activation))
            shared_reg_deep_list.append(shared_reg_out_layer)

        # 3.7. Output layer: Softmax
        shared_FC_soft = TimeDistributed(Dense(params['OUTPUT_VOCABULARY_SIZE'],
                                               activation=params['CLASSIFIER_ACTIVATION'],
                                               W_regularizer=l2(params['WEIGHT_DECAY']),
                                               name=params['CLASSIFIER_ACTIVATION']
                                               ),
                                         name=self.ids_outputs[0])
        softout = shared_FC_soft(out_layer)

        self.model = Model(input=[video, next_words], output=softout)

        ##################################################################
        #               BEAM SEARCH OPTIMIZED MODEL                      #
        ##################################################################
        # Now that we have the basic training model ready, let's prepare the model for applying decoding
        # The beam-search model will include all the minimum required set of layers (decoder stage) which offer the
        # possibility to generate the next state in the sequence given a pre-processed input (encoder stage)
        if params['BEAM_SEARCH']:
            # First, we need a model that outputs the preprocessed input + initial h state
            # for applying the initial forward pass
            model_init_input = [video, next_words]
            model_init_output = [softout, input_video, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_init_output.append(h_memory)

            self.model_init = Model(input=model_init_input, output=model_init_output)

            # Store inputs and outputs names for model_init
            self.ids_inputs_init = self.ids_inputs
            # first output must be the output probs.
            self.ids_outputs_init = self.ids_outputs + ['preprocessed_input', 'next_state']
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_outputs_init.append('next_memory')

            # Second, we need to build an additional model with the capability to have the following inputs:
            #   - preprocessed_input
            #   - prev_word
            #   - prev_state
            # and the following outputs:
            #   - softmax probabilities
            #   - next_state
            preprocessed_size = params['IMG_FEAT_SIZE']

            # Define inputs
            preprocessed_annotations = Input(name='preprocessed_input',
                                             shape=tuple([params['NUM_FRAMES'], preprocessed_size]))
            prev_h_state = Input(name='prev_state', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
            input_attentional_decoder = [emb, preprocessed_annotations, prev_h_state]

            if params['RNN_TYPE'] == 'LSTM':
                prev_h_memory = Input(name='prev_memory', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
                input_attentional_decoder.append(prev_h_memory)
            # Apply decoder
            rnn_output = sharedAttRNNCond(input_attentional_decoder)
            proj_h = rnn_output[0]
            x_att = rnn_output[1]
            alphas = rnn_output[2]
            h_state = rnn_output[3]
            if params['RNN_TYPE'] == 'LSTM':
                h_memory = rnn_output[4]
            for reg in shared_reg_proj_h:
                proj_h = reg(proj_h)

            out_layer_mlp = shared_FC_mlp(proj_h)
            out_layer_ctx = shared_FC_ctx(x_att)
            out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
            out_layer_emb = shared_FC_emb(emb)

            for (reg_out_layer_mlp, reg_out_layer_ctx, reg_out_layer_emb) in zip(shared_reg_out_layer_mlp,
                                                                                 shared_reg_out_layer_ctx,
                                                                                 shared_reg_out_layer_emb):
                out_layer_mlp = reg_out_layer_mlp(out_layer_mlp)
                out_layer_ctx = reg_out_layer_ctx(out_layer_ctx)
                out_layer_emb = reg_out_layer_emb(out_layer_emb)

            additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb],
                                      mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='additional_input_model_next')
            out_layer = shared_activation_tanh(additional_output)

            for (deep_out_layer, reg_list) in zip(shared_deep_list, shared_reg_deep_list):
                out_layer = deep_out_layer(out_layer)
                for reg in reg_list:
                    out_layer = reg(out_layer)

            # Softmax
            softout = shared_FC_soft(out_layer)
            model_next_inputs = [next_words, preprocessed_annotations, prev_h_state]
            model_next_outputs = [softout, preprocessed_annotations, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_next_inputs.append(prev_h_memory)
                model_next_outputs.append(h_memory)

            self.model_next = Model(input=model_next_inputs,
                                    output=model_next_outputs)

            # Store inputs and outputs names for model_next
            # first input must be previous word
            self.ids_inputs_next = [self.ids_inputs[1]] + ['preprocessed_input', 'prev_state']
            # first output must be the output probs.
            self.ids_outputs_next = self.ids_outputs + ['preprocessed_input', 'next_state']

            # Input -> Output matchings from model_init to model_next and from model_next to model_next
            self.matchings_init_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'next_state': 'prev_state'}
            self.matchings_next_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'next_state': 'prev_state'}
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_inputs_next.append('prev_memory')
                self.ids_outputs_next.append('next_memory')
                self.matchings_init_to_next['next_memory'] = 'prev_memory'
                self.matchings_next_to_next['next_memory'] = 'prev_memory'

    def TemporallyLinkedVideoDescriptionNoAtt(self, params):
        """
        Video captioning with:
            * Attention mechansim on video frames
            * Conditional LSTM for processing the video
            * Feed forward layers:
                + Context projected to output
                + Last word projected to output

            * LSTM on output of previous sequence/video

        :param params:
        :return:
        """
        # Prepare variables for temporally linked samples
        self.ids_temporally_linked_inputs = [self.ids_inputs[2]]
        self.matchings_sample_to_next_sample = {self.ids_outputs[0]: self.ids_inputs[2]}

        # Video model
        # video = Input(name=self.ids_inputs[0], shape=tuple([params['NUM_FRAMES'], params['IMG_FEAT_SIZE']]))
        video = Input(name=self.ids_inputs[0], shape=tuple([None, params['IMG_FEAT_SIZE']]))
        input_video = video
        ##################################################################
        #                       ENCODER
        ##################################################################
        for activation, dimension in params['IMG_EMBEDDING_LAYERS']:
            input_video = TimeDistributed(Dense(dimension, name='%s_1' % activation, activation=activation,
                                                W_regularizer=l2(params['WEIGHT_DECAY'])))(input_video)
            input_video = Regularize(input_video, params, name='%s_1' % activation)

        if params['ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_ENCODER']:
                encoder = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                 W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                 dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                 return_sequences=True),
                                        name='bidirectional_encoder_' + params['RNN_TYPE'],
                                        merge_mode='concat')(input_video)
            else:
                encoder = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                   W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                   dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                   return_sequences=True,
                                                   name='encoder_' + params['RNN_TYPE'])(input_video)
            input_video = merge([input_video, encoder], mode='concat', concat_axis=2)
            input_video = Regularize(input_video, params, name='input_video')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_ENCODER']:
                    current_input_video = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                                 W_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 U_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 b_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 dropout_W=params[
                                                                                     'RECURRENT_DROPOUT_P'] if params[
                                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                                 dropout_U=params[
                                                                                     'RECURRENT_DROPOUT_P'] if params[
                                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                                 return_sequences=True,
                                                                                 ),
                                                        merge_mode='concat',
                                                        name='bidirectional_encoder_' + str(n_layer))(input_video)
                else:
                    current_input_video = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                   W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                   dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                   return_sequences=True,
                                                                   name='encoder_' + str(n_layer))(input_video)

                current_input_video = Regularize(current_input_video, params, name='input_video_' + str(n_layer))
                input_video = merge([input_video, current_input_video], mode='sum')

        # Previously generated words as inputs for training
        next_words = Input(name=self.ids_inputs[1], batch_shape=tuple([None, None]), dtype='int32')
        shared_emb = Embedding(params['OUTPUT_VOCABULARY_SIZE'],
                               params['TARGET_TEXT_EMBEDDING_SIZE'],
                               name='target_word_embedding',
                               W_regularizer=l2(params['WEIGHT_DECAY']),
                               trainable=self.trg_embedding_weights_trainable,
                               weights=self.trg_embedding_weights,
                               mask_zero=True)
        emb = shared_emb(next_words)
        emb = Regularize(emb, params, name='target_word_embedding')

        # Previously generated description from temporally-linked sample
        prev_desc = Input(name=self.ids_inputs[2], batch_shape=tuple([None, None]), dtype='int32')
        # previous description and previously generated words share the same embedding
        prev_desc_emb = shared_emb(prev_desc)
        # LSTM for encoding the previous description
        if params['PREV_SENT_ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_PREV_SENT_ENCODER']:
                prev_desc_enc = Bidirectional(eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                       W_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       U_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       b_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       return_sequences=False),
                                              name='prev_desc_emb_bidirectional_encoder_' + params['RNN_TYPE'],
                                              merge_mode='concat')(prev_desc_emb)
            else:
                prev_desc_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                         W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         return_sequences=False,
                                                         name='prev_desc_emb_encoder_' + params['RNN_TYPE'])(
                    prev_desc_emb)
            prev_desc_enc = Regularize(prev_desc_enc, params, name='prev_desc_enc')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_PREV_SENT_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_PREV_SENT_ENCODER']:
                    current_prev_desc_enc = Bidirectional(
                        eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                 W_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 U_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 b_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 dropout_W=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 dropout_U=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 return_sequences=False,
                                                 ),
                        merge_mode='concat',
                        name='prev_desc_emb_bidirectional_encoder_' + str(n_layer))(prev_desc_emb)
                else:
                    current_prev_desc_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                     W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     return_sequences=False,
                                                                     name='prev_desc_emb_encoder_' + str(n_layer))(
                        prev_desc_emb)

                current_prev_desc_enc = Regularize(current_prev_desc_enc, params, name='prev_desc_enc_' + str(n_layer))
                prev_desc_enc = merge([prev_desc_enc, current_prev_desc_enc], mode='sum')

        # LSTM initialization perceptrons with ctx mean
        # 3.2. Decoder's RNN initialization perceptrons with ctx mean
        ctx_mean = Lambda(lambda x: K.mean(x, axis=1),
                          output_shape=lambda s: (s[0], s[2]), name='lambda_mean')(input_video)

        if len(params['INIT_LAYERS']) > 0:
            for n_layer_init in range(len(params['INIT_LAYERS']) - 1):
                ctx_mean = Dense(params['DECODER_HIDDEN_SIZE'], name='init_layer_%d' % n_layer_init,
                                 W_regularizer=l2(params['WEIGHT_DECAY']),
                                 activation=params['INIT_LAYERS'][n_layer_init]
                                 )(ctx_mean)
                ctx_mean = Regularize(ctx_mean, params, name='ctx' + str(n_layer_init))

            initial_state = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_state',
                                  W_regularizer=l2(params['WEIGHT_DECAY']),
                                  activation=params['INIT_LAYERS'][-1]
                                  )(ctx_mean)
            initial_state = Regularize(initial_state, params, name='initial_state')
            input_attentional_decoder = [emb, input_video, prev_desc_enc, initial_state]

            if params['RNN_TYPE'] == 'LSTM':
                initial_memory = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_memory',
                                       W_regularizer=l2(params['WEIGHT_DECAY']),
                                       activation=params['INIT_LAYERS'][-1])(ctx_mean)
                initial_memory = Regularize(initial_memory, params, name='initial_memory')
                input_attentional_decoder.append(initial_memory)
        else:
            input_attentional_decoder = [emb, input_video, prev_desc_enc]
        ##################################################################
        #                       DECODER
        ##################################################################

        # 3.3. Attentional decoder
        sharedAttRNNCond = eval('Att' + params['RNN_TYPE'] + 'Cond2Inputs')(params['DECODER_HIDDEN_SIZE'],
                                                                            W_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            U_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            V_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            b_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Ua_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            ba_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                            params['USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                            params['USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_V=params['RECURRENT_DROPOUT_P'] if
                                                                            params['USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_wa=params['DROPOUT_P'] if params[
                                                                                'USE_DROPOUT'] else None,
                                                                            dropout_Wa=params['DROPOUT_P'] if params[
                                                                                'USE_DROPOUT'] else None,
                                                                            dropout_Ua=params['DROPOUT_P'] if params[
                                                                                'USE_DROPOUT'] else None,
                                                                            return_sequences=True,
                                                                            return_extra_variables=True,
                                                                            return_states=True,
                                                                            attend_on_both=False,
                                                                            name='decoder_Att' + params[
                                                                                'RNN_TYPE'] + 'Cond')

        rnn_output = sharedAttRNNCond(input_attentional_decoder)
        proj_h = rnn_output[0]
        x_att = rnn_output[1]
        alphas = rnn_output[2]
        prev_desc_att = rnn_output[3]
        prev_desc_alphas = rnn_output[4]
        h_state = rnn_output[5]

        if params['RNN_TYPE'] == 'LSTM':
            h_memory = rnn_output[6]

        [proj_h, shared_reg_proj_h] = Regularize(proj_h, params, shared_layers=True, name='proj_h0')

        ### FC layers before merge
        shared_FC_mlp = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_lstm')
        out_layer_mlp = shared_FC_mlp(proj_h)
        shared_FC_ctx = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_ctx')
        out_layer_ctx = shared_FC_ctx(x_att)

        shared_Lambda_Permute = PermuteGeneral((1, 0, 2))
        out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
        shared_FC_emb = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear'),
                                        name='logit_emb')
        out_layer_emb = shared_FC_emb(emb)

        shared_FC_prev = Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                               W_regularizer=l2(params['WEIGHT_DECAY']),
                               activation='linear', name='logit_prev')
        out_layer_prev = shared_FC_prev(prev_desc_enc)
        # Add broadcastable dimension before merging
        shared_Lambda_Broadcast = Lambda(lambda x: K.expand_dims(x, dim=1),
                                         output_shape=lambda s: tuple([s[0]] + [None] + [s[1]]),
                                         name='lambda_broadcast')

        out_layer_prev = shared_Lambda_Broadcast(out_layer_prev)

        ### Regularization of FC outputs
        [out_layer_mlp, shared_reg_out_layer_mlp] = Regularize(out_layer_mlp, params,
                                                               shared_layers=True, name='out_layer_mlp')
        [out_layer_ctx, shared_reg_out_layer_ctx] = Regularize(out_layer_ctx, params,
                                                               shared_layers=True, name='out_layer_ctx')
        [out_layer_emb, shared_reg_out_layer_emb] = Regularize(out_layer_emb, params,
                                                               shared_layers=True, name='out_layer_emb')
        [out_layer_prev, shared_reg_out_layer_prev] = Regularize(out_layer_prev, params,
                                                                 shared_layers=True, name='out_layer_prev')

        ### Merge of FC outputs
        additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev],
                                  mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='additional_input')
        # tanh activation
        shared_activation_tanh = Activation('tanh')
        out_layer = shared_activation_tanh(additional_output)

        ### Final FCs and prediction
        shared_deep_list = []
        shared_reg_deep_list = []
        # 3.6 Optional deep ouput layer
        for i, (activation, dimension) in enumerate(params['DEEP_OUTPUT_LAYERS']):
            if activation.lower() == 'maxout':
                shared_deep_list.append(TimeDistributed(MaxoutDense(dimension,
                                                                    W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name='maxout_%d' % i))
            else:
                shared_deep_list.append(TimeDistributed(Dense(dimension, activation=activation,
                                                              W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name=activation + '_%d' % i))
            out_layer = shared_deep_list[-1](out_layer)
            [out_layer, shared_reg_out_layer] = Regularize(out_layer,
                                                           params, shared_layers=True,
                                                           name='out_layer' + str(activation))
            shared_reg_deep_list.append(shared_reg_out_layer)

        # 3.7. Output layer: Softmax
        shared_FC_soft = TimeDistributed(Dense(params['OUTPUT_VOCABULARY_SIZE'],
                                               activation=params['CLASSIFIER_ACTIVATION'],
                                               W_regularizer=l2(params['WEIGHT_DECAY']),
                                               name=params['CLASSIFIER_ACTIVATION']
                                               ),
                                         name=self.ids_outputs[0])
        softout = shared_FC_soft(out_layer)

        self.model = Model(input=[video, next_words, prev_desc], output=softout)

        ##################################################################
        #               BEAM SEARCH OPTIMIZED MODEL                      #
        ##################################################################
        # Now that we have the basic training model ready, let's prepare the model for applying decoding
        # The beam-search model will include all the minimum required set of layers (decoder stage) which offer the
        # possibility to generate the next state in the sequence given a pre-processed input (encoder stage)
        if params['BEAM_SEARCH'] and params['OPTIMIZED_SEARCH']:
            # First, we need a model that outputs the preprocessed input + initial h state
            # for applying the initial forward pass
            model_init_input = [video, next_words, prev_desc]
            model_init_output = [softout, input_video, prev_desc_enc, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_init_output.append(h_memory)

            self.model_init = Model(input=model_init_input, output=model_init_output)

            # Store inputs and outputs names for model_init
            self.ids_inputs_init = self.ids_inputs
            # first output must be the output probs.
            self.ids_outputs_init = self.ids_outputs + ['preprocessed_input', 'preprocessed_input2', 'next_state']
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_outputs_init.append('next_memory')

            # Second, we need to build an additional model with the capability to have the following inputs:
            #   - preprocessed_input
            #   - prev_word
            #   - prev_state
            # and the following outputs:
            #   - softmax probabilities
            #   - next_state
            if params['ENCODER_HIDDEN_SIZE'] > 0:
                if params['BIDIRECTIONAL_ENCODER']:
                    preprocessed_size = params['ENCODER_HIDDEN_SIZE'] * 2 + params['IMG_FEAT_SIZE']
                else:
                    preprocessed_size = params['ENCODER_HIDDEN_SIZE'] + params['IMG_FEAT_SIZE']
            else:
                preprocessed_size = params['IMG_FEAT_SIZE']

            if params['PREV_SENT_ENCODER_HIDDEN_SIZE'] > 0:
                if params['BIDIRECTIONAL_PREV_SENT_ENCODER']:
                    preprocessed_size_prev_desc = params['PREV_SENT_ENCODER_HIDDEN_SIZE'] * 2
                else:
                    preprocessed_size_prev_desc = params['PREV_SENT_ENCODER_HIDDEN_SIZE']

            # Define inputs
            preprocessed_annotations = Input(name='preprocessed_input',
                                             shape=tuple([None, preprocessed_size]))
            preprocessed_prev_description = Input(name='preprocessed_input2',
                                                  shape=tuple([preprocessed_size_prev_desc]))
            prev_h_state = Input(name='prev_state', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
            input_attentional_decoder = [emb, preprocessed_annotations, preprocessed_prev_description, prev_h_state]

            if params['RNN_TYPE'] == 'LSTM':
                prev_h_memory = Input(name='prev_memory', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
                input_attentional_decoder.append(prev_h_memory)
            # Apply decoder
            rnn_output = sharedAttRNNCond(input_attentional_decoder)
            proj_h = rnn_output[0]
            x_att = rnn_output[1]
            alphas = rnn_output[2]
            prev_desc_att = rnn_output[3]
            prev_desc_alphas = rnn_output[4]
            h_state = rnn_output[5]
            if params['RNN_TYPE'] == 'LSTM':
                h_memory = rnn_output[6]
            for reg in shared_reg_proj_h:
                proj_h = reg(proj_h)

            out_layer_mlp = shared_FC_mlp(proj_h)
            out_layer_ctx = shared_FC_ctx(x_att)
            out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
            out_layer_emb = shared_FC_emb(emb)
            out_layer_prev = shared_FC_prev(preprocessed_prev_description)
            out_layer_prev = shared_Lambda_Broadcast(out_layer_prev)

            for (reg_out_layer_mlp, reg_out_layer_ctx, reg_out_layer_emb, reg_out_layer_prev) in zip(
                    shared_reg_out_layer_mlp,
                    shared_reg_out_layer_ctx,
                    shared_reg_out_layer_emb,
                    shared_reg_out_layer_prev):
                out_layer_mlp = reg_out_layer_mlp(out_layer_mlp)
                out_layer_ctx = reg_out_layer_ctx(out_layer_ctx)
                out_layer_emb = reg_out_layer_emb(out_layer_emb)
                out_layer_prev = reg_out_layer_prev(out_layer_prev)

            additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev],
                                      mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='additional_input_model_next')
            out_layer = shared_activation_tanh(additional_output)

            for (deep_out_layer, reg_list) in zip(shared_deep_list, shared_reg_deep_list):
                out_layer = deep_out_layer(out_layer)
                for reg in reg_list:
                    out_layer = reg(out_layer)

            # Softmax
            softout = shared_FC_soft(out_layer)
            model_next_inputs = [next_words, preprocessed_annotations, preprocessed_prev_description, prev_h_state]
            model_next_outputs = [softout, preprocessed_annotations, preprocessed_prev_description, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_next_inputs.append(prev_h_memory)
                model_next_outputs.append(h_memory)

            self.model_next = Model(input=model_next_inputs, output=model_next_outputs)

            # Store inputs and outputs names for model_next
            # first input must be previous word
            self.ids_inputs_next = [self.ids_inputs[1]] + ['preprocessed_input', 'preprocessed_input2', 'prev_state']
            # first output must be the output probs.
            self.ids_outputs_next = self.ids_outputs + ['preprocessed_input', 'preprocessed_input2', 'next_state']

            # Input -> Output matchings from model_init to model_next and from model_next to model_next
            self.matchings_init_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'preprocessed_input2': 'preprocessed_input2',
                                           'next_state': 'prev_state'}
            self.matchings_next_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'preprocessed_input2': 'preprocessed_input2',
                                           'next_state': 'prev_state'}
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_inputs_next.append('prev_memory')
                self.ids_outputs_next.append('next_memory')
                self.matchings_init_to_next['next_memory'] = 'prev_memory'
                self.matchings_next_to_next['next_memory'] = 'prev_memory'

    def TemporallyLinkedVideoDescriptionAtt(self, params):
        """
        Video captioning with:
            * Attention mechanism on video frames
            * Conditional LSTM for processing the video
            * Feed forward layers projected to output:
                + Context
                + Last word
                + LSTM's hidden state
                + Previous output

            * LSTM on output of previous sequence/video
            * Attention mechanism on words of previous output

        :param params:
        :return:
        """
        # Prepare variables for temporally linked samples
        self.ids_temporally_linked_inputs = [self.ids_inputs[2]]
        self.matchings_sample_to_next_sample = {self.ids_outputs[0]: self.ids_inputs[2]}

        # Video model
        # video = Input(name=self.ids_inputs[0], shape=tuple([params['NUM_FRAMES'], params['IMG_FEAT_SIZE']]))
        video = Input(name=self.ids_inputs[0], shape=tuple([None, params['IMG_FEAT_SIZE']]))
        input_video = video
        ##################################################################
        #                       ENCODER
        ##################################################################
        for activation, dimension in params['IMG_EMBEDDING_LAYERS']:
            input_video = TimeDistributed(Dense(dimension, name='%s_1' % activation, activation=activation,
                                                W_regularizer=l2(params['WEIGHT_DECAY'])))(input_video)
            input_video = Regularize(input_video, params, name='%s_1' % activation)

        if params['ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_ENCODER']:
                encoded_video = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                       W_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       U_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       b_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       return_sequences=True),
                                              name='bidirectional_encoder_' + params['RNN_TYPE'],
                                              merge_mode='concat')(input_video)
            else:
                encoded_video = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                         W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         return_sequences=True,
                                                         name='encoder_' + params['RNN_TYPE'])(input_video)
            encoded_video = Regularize(encoded_video, params, name='input_video')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_ENCODER']:
                    current_encoded_video = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                                   W_regularizer=l2(
                                                                                       params[
                                                                                           'RECURRENT_WEIGHT_DECAY']),
                                                                                   U_regularizer=l2(
                                                                                       params[
                                                                                           'RECURRENT_WEIGHT_DECAY']),
                                                                                   b_regularizer=l2(
                                                                                       params[
                                                                                           'RECURRENT_WEIGHT_DECAY']),
                                                                                   dropout_W=params[
                                                                                       'RECURRENT_DROPOUT_P'] if params[
                                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                                   dropout_U=params[
                                                                                       'RECURRENT_DROPOUT_P'] if params[
                                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                                   return_sequences=True,
                                                                                   ),
                                                          merge_mode='concat',
                                                          name='bidirectional_encoder_' + str(n_layer))(encoded_video)
                else:
                    current_encoded_video = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                     W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     return_sequences=True,
                                                                     name='encoder_' + str(n_layer))(encoded_video)

                current_encoded_video = Regularize(current_encoded_video, params, name='input_video_' + str(n_layer))
                encoded_video = merge([encoded_video, current_encoded_video], mode='sum')

            input_video = merge([input_video, encoded_video], mode='concat', concat_axis=2)

        # Previously generated words as inputs for training
        next_words = Input(name=self.ids_inputs[1], batch_shape=tuple([None, None]), dtype='int32')
        shared_emb = Embedding(params['OUTPUT_VOCABULARY_SIZE'],
                               params['TARGET_TEXT_EMBEDDING_SIZE'],
                               name='target_word_embedding',
                               W_regularizer=l2(params['WEIGHT_DECAY']),
                               trainable=self.trg_embedding_weights_trainable,
                               weights=self.trg_embedding_weights,
                               mask_zero=True)
        emb = shared_emb(next_words)
        emb = Regularize(emb, params, name='target_word_embedding')

        if '-video' in params['DATASET_NAME']:
            # Video from the previous event
            prev_desc = Input(name=self.ids_inputs[2], shape=tuple([None, params['IMG_FEAT_SIZE']]))
            prev_desc_emb = prev_desc
        else:
            # Previously generated description from temporally-linked sample
            prev_desc = Input(name=self.ids_inputs[2], batch_shape=tuple([None, None]), dtype='int32')
            # previous description and previously generated words share the same embedding
            prev_desc_emb = shared_emb(prev_desc)

        # LSTM for encoding the previous description
        if params['PREV_SENT_ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_PREV_SENT_ENCODER']:
                prev_desc_enc = Bidirectional(eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                       W_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       U_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       b_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       return_sequences=True),
                                              name='prev_desc_emb_bidirectional_encoder_' + params['RNN_TYPE'],
                                              merge_mode='concat')(prev_desc_emb)
            else:
                prev_desc_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                         W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         return_sequences=True,
                                                         name='prev_desc_emb_encoder_' + params['RNN_TYPE'])(
                    prev_desc_emb)
            prev_desc_enc = Regularize(prev_desc_enc, params, name='prev_desc_enc')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_PREV_SENT_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_PREV_SENT_ENCODER']:
                    current_prev_desc_enc = Bidirectional(
                        eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                 W_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 U_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 b_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 dropout_W=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 dropout_U=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 return_sequences=True,
                                                 ),
                        merge_mode='concat',
                        name='prev_desc_emb_bidirectional_encoder_' + str(n_layer))(prev_desc_emb)
                else:
                    current_prev_desc_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                     W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     return_sequences=True,
                                                                     name='prev_desc_emb_encoder_' + str(n_layer))(
                        prev_desc_emb)

                current_prev_desc_enc = Regularize(current_prev_desc_enc, params, name='prev_desc_enc_' + str(n_layer))
                prev_desc_enc = merge([prev_desc_enc, current_prev_desc_enc], mode='sum')

        # LSTM initialization perceptrons with ctx mean
        # 3.2. Decoder's RNN initialization perceptrons with ctx mean
        ctx_mean = Lambda(lambda x: K.mean(x, axis=1),
                          output_shape=lambda s: (s[0], s[2]), name='lambda_mean')(input_video)

        if len(params['INIT_LAYERS']) > 0:
            for n_layer_init in range(len(params['INIT_LAYERS']) - 1):
                ctx_mean = Dense(params['DECODER_HIDDEN_SIZE'], name='init_layer_%d' % n_layer_init,
                                 W_regularizer=l2(params['WEIGHT_DECAY']),
                                 activation=params['INIT_LAYERS'][n_layer_init]
                                 )(ctx_mean)
                ctx_mean = Regularize(ctx_mean, params, name='ctx' + str(n_layer_init))

            initial_state = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_state',
                                  W_regularizer=l2(params['WEIGHT_DECAY']),
                                  activation=params['INIT_LAYERS'][-1]
                                  )(ctx_mean)
            initial_state = Regularize(initial_state, params, name='initial_state')
            input_attentional_decoder = [emb, input_video, prev_desc_enc, initial_state]

            if params['RNN_TYPE'] == 'LSTM':
                initial_memory = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_memory',
                                       W_regularizer=l2(params['WEIGHT_DECAY']),
                                       activation=params['INIT_LAYERS'][-1])(ctx_mean)
                initial_memory = Regularize(initial_memory, params, name='initial_memory')
                input_attentional_decoder.append(initial_memory)
        else:
            input_attentional_decoder = [emb, input_video, prev_desc_enc]

        ##################################################################
        #                       DECODER
        ##################################################################

        # 3.3. Attentional decoder
        sharedAttRNNCond = eval('Att' + params['RNN_TYPE'] + 'Cond2Inputs')(params['DECODER_HIDDEN_SIZE'],
                                                                            W_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            U_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            V_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            b_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Ua_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            ba_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            wa2_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Wa2_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Ua2_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            ba2_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_V=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_wa=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_Wa=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_Ua=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            return_sequences=True,
                                                                            return_extra_variables=True,
                                                                            return_states=True,
                                                                            attend_on_both=True,
                                                                            name='decoder_Att' + params[
                                                                                'RNN_TYPE'] + 'Cond2Inputs')

        rnn_output = sharedAttRNNCond(input_attentional_decoder)
        proj_h = rnn_output[0]
        x_att = rnn_output[1]
        alphas = rnn_output[2]
        prev_desc_att = rnn_output[3]
        prev_desc_alphas = rnn_output[4]
        h_state = rnn_output[5]
        if params['RNN_TYPE'] == 'LSTM':
            h_memory = rnn_output[6]

        [proj_h, shared_reg_proj_h] = Regularize(proj_h, params, shared_layers=True, name='proj_h0')

        ### FC layers before merge
        shared_FC_mlp = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_lstm')
        out_layer_mlp = shared_FC_mlp(proj_h)
        shared_FC_ctx = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_ctx')
        out_layer_ctx = shared_FC_ctx(x_att)

        shared_Lambda_Permute = PermuteGeneral((1, 0, 2))
        out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
        shared_FC_emb = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear'),
                                        name='logit_emb')
        out_layer_emb = shared_FC_emb(emb)

        shared_FC_prev = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                               W_regularizer=l2(params['WEIGHT_DECAY']),
                                               activation='linear'),
                                         name='logit_prev')
        out_layer_prev = shared_FC_prev(prev_desc_att)
        out_layer_prev = shared_Lambda_Permute(out_layer_prev)

        ### Regularization of FC outputs
        [out_layer_mlp, shared_reg_out_layer_mlp] = Regularize(out_layer_mlp, params,
                                                               shared_layers=True, name='out_layer_mlp')
        [out_layer_ctx, shared_reg_out_layer_ctx] = Regularize(out_layer_ctx, params,
                                                               shared_layers=True, name='out_layer_ctx')
        [out_layer_emb, shared_reg_out_layer_emb] = Regularize(out_layer_emb, params,
                                                               shared_layers=True, name='out_layer_emb')
        [out_layer_prev, shared_reg_out_layer_prev] = Regularize(out_layer_prev, params,
                                                                 shared_layers=True, name='out_layer_prev')

        ### Merge of FC outputs
        if params['WEIGHTED_MERGE']:
            shared_merge = WeightedMerge(mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'],
                                         lambdas_regularizer=l2(params['WEIGHT_DECAY']),
                                         name='additional_input')
            additional_output = shared_merge([out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev])
        else:
            additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev],
                                      mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='additional_input')

        # tanh activation
        shared_activation_tanh = Activation('tanh')
        out_layer = shared_activation_tanh(additional_output)

        ### Final FCs and prediction
        shared_deep_list = []
        shared_reg_deep_list = []
        # 3.6 Optional deep ouput layer
        for i, (activation, dimension) in enumerate(params['DEEP_OUTPUT_LAYERS']):
            if activation.lower() == 'maxout':
                shared_deep_list.append(TimeDistributed(MaxoutDense(dimension,
                                                                    W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name='maxout_%d' % i))
            else:
                shared_deep_list.append(TimeDistributed(Dense(dimension, activation=activation,
                                                              W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name=activation + '_%d' % i))
            out_layer = shared_deep_list[-1](out_layer)
            [out_layer, shared_reg_out_layer] = Regularize(out_layer,
                                                           params, shared_layers=True,
                                                           name='out_layer' + str(activation))
            shared_reg_deep_list.append(shared_reg_out_layer)

        # 3.7. Output layer: Softmax
        shared_FC_soft = TimeDistributed(Dense(params['OUTPUT_VOCABULARY_SIZE'],
                                               activation=params['CLASSIFIER_ACTIVATION'],
                                               W_regularizer=l2(params['WEIGHT_DECAY']),
                                               name=params['CLASSIFIER_ACTIVATION']),
                                         name=self.ids_outputs[0])
        softout = shared_FC_soft(out_layer)

        self.model = Model(input=[video, next_words, prev_desc], output=softout)

        ##################################################################
        #               BEAM SEARCH OPTIMIZED MODEL                      #
        ##################################################################
        # Now that we have the basic training model ready, let's prepare the model for applying decoding
        # The beam-search model will include all the minimum required set of layers (decoder stage) which offer the
        # possibility to generate the next state in the sequence given a pre-processed input (encoder stage)
        if params['BEAM_SEARCH'] and params['OPTIMIZED_SEARCH']:
            # First, we need a model that outputs both preprocessed inputs + initial h state
            # for applying the initial forward pass
            model_init_input = [video, next_words, prev_desc]
            model_init_output = [softout, input_video, prev_desc_enc, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_init_output.append(h_memory)

            self.model_init = Model(input=model_init_input, output=model_init_output)

            # Store inputs and outputs names for model_init
            self.ids_inputs_init = self.ids_inputs
            # first output must be the output probs.
            self.ids_outputs_init = self.ids_outputs + ['preprocessed_input', 'preprocessed_input2', 'next_state']
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_outputs_init.append('next_memory')

            # Second, we need to build an additional model with the capability to have the following inputs:
            #   - preprocessed_input
            #   - preprocessed_input2
            #   - prev_word
            #   - prev_state
            #   - prev_memory (only if using LSTM)
            # and the following outputs:
            #   - softmax probabilities
            #   - next_state
            if params['ENCODER_HIDDEN_SIZE'] > 0:
                if params['BIDIRECTIONAL_ENCODER']:
                    preprocessed_size = params['ENCODER_HIDDEN_SIZE'] * 2 + params['IMG_FEAT_SIZE']
                else:
                    preprocessed_size = params['ENCODER_HIDDEN_SIZE'] + params['IMG_FEAT_SIZE']
            else:
                preprocessed_size = params['IMG_FEAT_SIZE']

            if params['PREV_SENT_ENCODER_HIDDEN_SIZE'] > 0:
                if params['BIDIRECTIONAL_PREV_SENT_ENCODER']:
                    preprocessed_size_prev_desc = params['PREV_SENT_ENCODER_HIDDEN_SIZE'] * 2
                else:
                    preprocessed_size_prev_desc = params['PREV_SENT_ENCODER_HIDDEN_SIZE']

            # Define inputs
            preprocessed_annotations = Input(name='preprocessed_input',
                                             shape=tuple([None, preprocessed_size]))
            preprocessed_prev_description = Input(name='preprocessed_input2',
                                                  shape=tuple([None, preprocessed_size_prev_desc]))
            prev_h_state = Input(name='prev_state', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
            input_attentional_decoder = [emb, preprocessed_annotations, preprocessed_prev_description, prev_h_state]

            if params['RNN_TYPE'] == 'LSTM':
                prev_h_memory = Input(name='prev_memory', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
                input_attentional_decoder.append(prev_h_memory)
            # Apply decoder
            rnn_output = sharedAttRNNCond(input_attentional_decoder)
            proj_h = rnn_output[0]
            x_att = rnn_output[1]
            alphas = rnn_output[2]
            prev_desc_att = rnn_output[3]
            prev_desc_alphas = rnn_output[4]
            h_state = rnn_output[5]
            if params['RNN_TYPE'] == 'LSTM':
                h_memory = rnn_output[6]
            for reg in shared_reg_proj_h:
                proj_h = reg(proj_h)

            out_layer_mlp = shared_FC_mlp(proj_h)
            out_layer_ctx = shared_FC_ctx(x_att)
            out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
            out_layer_emb = shared_FC_emb(emb)
            out_layer_prev = shared_FC_prev(prev_desc_att)
            out_layer_prev = shared_Lambda_Permute(out_layer_prev)

            for (reg_out_layer_mlp, reg_out_layer_ctx,
                 reg_out_layer_emb, reg_out_layer_prev) in zip(shared_reg_out_layer_mlp,
                                                               shared_reg_out_layer_ctx,
                                                               shared_reg_out_layer_emb,
                                                               shared_reg_out_layer_prev):
                out_layer_mlp = reg_out_layer_mlp(out_layer_mlp)
                out_layer_ctx = reg_out_layer_ctx(out_layer_ctx)
                out_layer_emb = reg_out_layer_emb(out_layer_emb)
                out_layer_prev = reg_out_layer_prev(out_layer_prev)

            if params['WEIGHTED_MERGE']:
                additional_output = shared_merge([out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev])
            else:
                additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev],
                                          mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'],
                                          name='additional_input_model_next')
            out_layer = shared_activation_tanh(additional_output)

            for (deep_out_layer, reg_list) in zip(shared_deep_list, shared_reg_deep_list):
                out_layer = deep_out_layer(out_layer)
                for reg in reg_list:
                    out_layer = reg(out_layer)

            # Softmax
            softout = shared_FC_soft(out_layer)
            model_next_inputs = [next_words, preprocessed_annotations, preprocessed_prev_description, prev_h_state]
            model_next_outputs = [softout, preprocessed_annotations, preprocessed_prev_description, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_next_inputs.append(prev_h_memory)
                model_next_outputs.append(h_memory)

            self.model_next = Model(input=model_next_inputs, output=model_next_outputs)

            # Store inputs and outputs names for model_next
            # first input must be previous word
            self.ids_inputs_next = [self.ids_inputs[1]] + ['preprocessed_input', 'preprocessed_input2', 'prev_state']
            # first output must be the output probs.
            self.ids_outputs_next = self.ids_outputs + ['preprocessed_input', 'preprocessed_input2', 'next_state']

            # Input -> Output matchings from model_init to model_next and from model_next to model_next
            self.matchings_init_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'preprocessed_input2': 'preprocessed_input2',
                                           'next_state': 'prev_state'}
            self.matchings_next_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'preprocessed_input2': 'preprocessed_input2',
                                           'next_state': 'prev_state'}
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_inputs_next.append('prev_memory')
                self.ids_outputs_next.append('next_memory')
                self.matchings_init_to_next['next_memory'] = 'prev_memory'
                self.matchings_next_to_next['next_memory'] = 'prev_memory'

    def TemporallyLinkedVideoDescriptionAttDoublePrev(self, params):
        """
        Video captioning with:
            * Attention mechanism on video frames
            * Conditional LSTM for processing the video
            * Feed forward layers projected to output:
                + Context
                + Last word
                + LSTM's hidden state
                + Previous output1 (text)
                + Previous output2 (video)

            * LSTM on output of previous sequence/video
            * Attention mechanism on words of previous output

        :param params:
        :return:
        """
        # Prepare variables for temporally linked samples
        self.ids_temporally_linked_inputs = [self.ids_inputs[2]]
        self.matchings_sample_to_next_sample = {self.ids_outputs[0]: self.ids_inputs[2]}

        # Video model
        # video = Input(name=self.ids_inputs[0], shape=tuple([params['NUM_FRAMES'], params['IMG_FEAT_SIZE']]))
        video = Input(name=self.ids_inputs[0], shape=tuple([None, params['IMG_FEAT_SIZE']]))
        input_video = video
        ##################################################################
        #                       ENCODER
        ##################################################################
        for activation, dimension in params['IMG_EMBEDDING_LAYERS']:
            input_video = TimeDistributed(Dense(dimension, name='%s_1' % activation, activation=activation,
                                                W_regularizer=l2(params['WEIGHT_DECAY'])))(input_video)
            input_video = Regularize(input_video, params, name='%s_1' % activation)

        if params['ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_ENCODER']:
                encoder = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                 W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                 dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                 return_sequences=True),
                                        name='bidirectional_encoder_' + params['RNN_TYPE'],
                                        merge_mode='concat')(input_video)
            else:
                encoder = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                   W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                   dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                   return_sequences=True,
                                                   name='encoder_' + params['RNN_TYPE'])(input_video)
            input_video = merge([input_video, encoder], mode='concat', concat_axis=2)
            input_video = Regularize(input_video, params, name='input_video')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_ENCODER']:
                    current_input_video = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                                 W_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 U_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 b_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 dropout_W=params[
                                                                                     'RECURRENT_DROPOUT_P'] if params[
                                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                                 dropout_U=params[
                                                                                     'RECURRENT_DROPOUT_P'] if params[
                                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                                 return_sequences=True,
                                                                                 ),
                                                        merge_mode='concat',
                                                        name='bidirectional_encoder_' + str(n_layer))(input_video)
                else:
                    current_input_video = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                   W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                   dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                   return_sequences=True,
                                                                   name='encoder_' + str(n_layer))(input_video)

                current_input_video = Regularize(current_input_video, params, name='input_video_' + str(n_layer))
                input_video = merge([input_video, current_input_video], mode='sum')

        # Previously generated words as inputs for training
        next_words = Input(name=self.ids_inputs[1], batch_shape=tuple([None, None]), dtype='int32')
        shared_emb = Embedding(params['OUTPUT_VOCABULARY_SIZE'],
                               params['TARGET_TEXT_EMBEDDING_SIZE'],
                               name='target_word_embedding',
                               W_regularizer=l2(params['WEIGHT_DECAY']),
                               trainable=self.trg_embedding_weights_trainable,
                               weights=self.trg_embedding_weights,
                               mask_zero=True)
        emb = shared_emb(next_words)
        emb = Regularize(emb, params, name='target_word_embedding')

        # Previously generated description from temporally-linked sample
        prev_desc = Input(name=self.ids_inputs[2], batch_shape=tuple([None, None]), dtype='int32')
        # previous description and previously generated words share the same embedding
        prev_desc_emb = shared_emb(prev_desc)

        # LSTM for encoding the previous description
        if params['PREV_SENT_ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_PREV_SENT_ENCODER']:
                prev_desc_enc = Bidirectional(eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                       W_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       U_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       b_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       return_sequences=True),
                                              name='prev_desc_emb_bidirectional_encoder_' + params['RNN_TYPE'],
                                              merge_mode='concat')(prev_desc_emb)
            else:
                prev_desc_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                         W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         return_sequences=True,
                                                         name='prev_desc_emb_encoder_' + params['RNN_TYPE'])(
                    prev_desc_emb)
            prev_desc_enc = Regularize(prev_desc_enc, params, name='prev_desc_enc')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_PREV_SENT_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_PREV_SENT_ENCODER']:
                    current_prev_desc_enc = Bidirectional(
                        eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                 W_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 U_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 b_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 dropout_W=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 dropout_U=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 return_sequences=True,
                                                 ),
                        merge_mode='concat',
                        name='prev_desc_emb_bidirectional_encoder_' + str(n_layer))(prev_desc_emb)
                else:
                    current_prev_desc_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                     W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     return_sequences=True,
                                                                     name='prev_desc_emb_encoder_' + str(n_layer))(
                        prev_desc_emb)

                current_prev_desc_enc = Regularize(current_prev_desc_enc, params, name='prev_desc_enc_' + str(n_layer))
                prev_desc_enc = merge([prev_desc_enc, current_prev_desc_enc], mode='sum')

        # Video from the previous event
        prev_vid = Input(name=self.ids_inputs[3], shape=tuple([None, params['IMG_FEAT_SIZE']]))
        prev_vid_emb = prev_vid

        # LSTM for encoding the previous description
        if params['PREV_SENT_ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_PREV_SENT_ENCODER']:
                prev_vid_enc = Bidirectional(eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                      W_regularizer=l2(
                                                                          params['RECURRENT_WEIGHT_DECAY']),
                                                                      U_regularizer=l2(
                                                                          params['RECURRENT_WEIGHT_DECAY']),
                                                                      b_regularizer=l2(
                                                                          params['RECURRENT_WEIGHT_DECAY']),
                                                                      dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                      params[
                                                                          'USE_RECURRENT_DROPOUT'] else None,
                                                                      dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                      params[
                                                                          'USE_RECURRENT_DROPOUT'] else None,
                                                                      return_sequences=True),
                                             name='prev_vid_emb_bidirectional_encoder_' + params['RNN_TYPE'],
                                             merge_mode='concat')(prev_vid_emb)
            else:
                prev_vid_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                        W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                        U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                        b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                        dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                            'USE_RECURRENT_DROPOUT'] else None,
                                                        dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                            'USE_RECURRENT_DROPOUT'] else None,
                                                        return_sequences=True,
                                                        name='prev_vid_emb_encoder_' + params['RNN_TYPE'])(prev_vid_emb)
            prev_vid_enc = Regularize(prev_vid_enc, params, name='prev_vid_enc')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_PREV_SENT_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_PREV_SENT_ENCODER']:
                    current_prev_vid_enc = Bidirectional(
                        eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                 W_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 U_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 b_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 dropout_W=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 dropout_U=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 return_sequences=True,
                                                 ),
                        merge_mode='concat',
                        name='prev_vid_emb_bidirectional_encoder_' + str(n_layer))(prev_vid_emb)
                else:
                    current_prev_vid_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                    W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                    U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                    b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                    dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                        'USE_RECURRENT_DROPOUT'] else None,
                                                                    dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                        'USE_RECURRENT_DROPOUT'] else None,
                                                                    return_sequences=True,
                                                                    name='prev_vid_emb_encoder_' + str(n_layer))(
                        prev_vid_emb)

                current_prev_vid_enc = Regularize(current_prev_vid_enc, params, name='prev_vid_enc_' + str(n_layer))
                prev_vid_enc = merge([prev_vid_enc, current_prev_vid_enc], mode='sum')

        # LSTM initialization perceptrons with ctx mean
        # 3.2. Decoder's RNN initialization perceptrons with ctx mean
        ctx_mean = Lambda(lambda x: K.mean(x, axis=1),
                          output_shape=lambda s: (s[0], s[2]), name='lambda_mean')(input_video)

        if len(params['INIT_LAYERS']) > 0:
            for n_layer_init in range(len(params['INIT_LAYERS']) - 1):
                ctx_mean = Dense(params['DECODER_HIDDEN_SIZE'], name='init_layer_%d' % n_layer_init,
                                 W_regularizer=l2(params['WEIGHT_DECAY']),
                                 activation=params['INIT_LAYERS'][n_layer_init]
                                 )(ctx_mean)
                ctx_mean = Regularize(ctx_mean, params, name='ctx' + str(n_layer_init))

            initial_state = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_state',
                                  W_regularizer=l2(params['WEIGHT_DECAY']),
                                  activation=params['INIT_LAYERS'][-1]
                                  )(ctx_mean)
            initial_state = Regularize(initial_state, params, name='initial_state')
            input_attentional_decoder = [emb, input_video, prev_desc_enc, prev_vid_enc, initial_state]

            if params['RNN_TYPE'] == 'LSTM':
                initial_memory = Dense(params['DECODER_HIDDEN_SIZE'], name='initial_memory',
                                       W_regularizer=l2(params['WEIGHT_DECAY']),
                                       activation=params['INIT_LAYERS'][-1])(ctx_mean)
                initial_memory = Regularize(initial_memory, params, name='initial_memory')
                input_attentional_decoder.append(initial_memory)
        else:
            input_attentional_decoder = [emb, input_video, prev_desc_enc, prev_vid_enc]

        ##################################################################
        #                       DECODER
        ##################################################################

        # 3.3. Attentional decoder
        sharedAttRNNCond = eval('Att' + params['RNN_TYPE'] + 'Cond3Inputs')(params['DECODER_HIDDEN_SIZE'],
                                                                            W_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            U_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            V_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            b_regularizer=l2(
                                                                                params['RECURRENT_WEIGHT_DECAY']),
                                                                            wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Wa_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Ua_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            ba_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            wa2_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Wa2_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            Ua2_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            ba2_regularizer=l2(params['WEIGHT_DECAY']),
                                                                            dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_V=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_wa=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_Wa=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            dropout_Ua=params['RECURRENT_DROPOUT_P'] if
                                                                            params[
                                                                                'USE_RECURRENT_DROPOUT'] else None,
                                                                            return_sequences=True,
                                                                            return_extra_variables=True,
                                                                            return_states=True,
                                                                            attend_on_both=True,
                                                                            name='decoder_Att' + params[
                                                                                'RNN_TYPE'] + 'Cond3Inputs')

        rnn_output = sharedAttRNNCond(input_attentional_decoder)
        proj_h = rnn_output[0]
        x_att = rnn_output[1]
        alphas = rnn_output[2]
        prev_desc_att = rnn_output[3]
        prev_desc_alphas = rnn_output[4]
        prev_vid_att = rnn_output[5]
        prev_vid_alphas = rnn_output[6]
        h_state = rnn_output[7]
        if params['RNN_TYPE'] == 'LSTM':
            h_memory = rnn_output[8]

        [proj_h, shared_reg_proj_h] = Regularize(proj_h, params, shared_layers=True, name='proj_h0')

        ### FC layers before merge
        shared_FC_mlp = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_lstm')
        out_layer_mlp = shared_FC_mlp(proj_h)
        shared_FC_ctx = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear',
                                              ), name='logit_ctx')
        out_layer_ctx = shared_FC_ctx(x_att)

        shared_Lambda_Permute = PermuteGeneral((1, 0, 2))
        out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
        shared_FC_emb = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                              W_regularizer=l2(params['WEIGHT_DECAY']),
                                              activation='linear'),
                                        name='logit_emb')
        out_layer_emb = shared_FC_emb(emb)

        shared_FC_prev = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                               W_regularizer=l2(params['WEIGHT_DECAY']),
                                               activation='linear'),
                                         name='logit_prev')
        out_layer_prev = shared_FC_prev(prev_desc_att)
        out_layer_prev = shared_Lambda_Permute(out_layer_prev)

        shared_FC_prev_vid = TimeDistributed(Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                                                   W_regularizer=l2(params['WEIGHT_DECAY']),
                                                   activation='linear'),
                                             name='logit_prev_vid')
        out_layer_prev_vid = shared_FC_prev_vid(prev_vid_att)
        out_layer_prev_vid = shared_Lambda_Permute(out_layer_prev_vid)

        ### Regularization of FC outputs
        [out_layer_mlp, shared_reg_out_layer_mlp] = Regularize(out_layer_mlp, params,
                                                               shared_layers=True, name='out_layer_mlp')
        [out_layer_ctx, shared_reg_out_layer_ctx] = Regularize(out_layer_ctx, params,
                                                               shared_layers=True, name='out_layer_ctx')
        [out_layer_emb, shared_reg_out_layer_emb] = Regularize(out_layer_emb, params,
                                                               shared_layers=True, name='out_layer_emb')
        [out_layer_prev, shared_reg_out_layer_prev] = Regularize(out_layer_prev, params,
                                                                 shared_layers=True, name='out_layer_prev')
        [out_layer_prev_vid, shared_reg_out_layer_prev_vid] = Regularize(out_layer_prev_vid, params,
                                                                         shared_layers=True, name='out_layer_prev_vid')

        ### Merge of FC outputs
        if params['WEIGHTED_MERGE']:
            shared_merge = WeightedMerge(mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'],
                                         lambdas_regularizer=l2(params['WEIGHT_DECAY']),
                                         name='additional_input')
            additional_output = shared_merge(
                [out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev, out_layer_prev_vid])
        else:
            additional_output = merge([out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev, out_layer_prev_vid],
                                      mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='additional_input')

        # tanh activation
        shared_activation_tanh = Activation('tanh')
        out_layer = shared_activation_tanh(additional_output)

        ### Final FCs and prediction
        shared_deep_list = []
        shared_reg_deep_list = []
        # 3.6 Optional deep ouput layer
        for i, (activation, dimension) in enumerate(params['DEEP_OUTPUT_LAYERS']):
            if activation.lower() == 'maxout':
                shared_deep_list.append(TimeDistributed(MaxoutDense(dimension,
                                                                    W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name='maxout_%d' % i))
            else:
                shared_deep_list.append(TimeDistributed(Dense(dimension, activation=activation,
                                                              W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name=activation + '_%d' % i))
            out_layer = shared_deep_list[-1](out_layer)
            [out_layer, shared_reg_out_layer] = Regularize(out_layer,
                                                           params, shared_layers=True,
                                                           name='out_layer' + str(activation))
            shared_reg_deep_list.append(shared_reg_out_layer)

        # 3.7. Output layer: Softmax
        shared_FC_soft = TimeDistributed(Dense(params['OUTPUT_VOCABULARY_SIZE'],
                                               activation=params['CLASSIFIER_ACTIVATION'],
                                               W_regularizer=l2(params['WEIGHT_DECAY']),
                                               name=params['CLASSIFIER_ACTIVATION']),
                                         name=self.ids_outputs[0])
        softout = shared_FC_soft(out_layer)

        self.model = Model(input=[video, next_words, prev_desc, prev_vid], output=softout)

        ##################################################################
        #               BEAM SEARCH OPTIMIZED MODEL                      #
        ##################################################################
        # Now that we have the basic training model ready, let's prepare the model for applying decoding
        # The beam-search model will include all the minimum required set of layers (decoder stage) which offer the
        # possibility to generate the next state in the sequence given a pre-processed input (encoder stage)
        if params['BEAM_SEARCH'] and params['OPTIMIZED_SEARCH']:
            # First, we need a model that outputs both preprocessed inputs + initial h state
            # for applying the initial forward pass
            model_init_input = [video, next_words, prev_desc, prev_vid]
            model_init_output = [softout, input_video, prev_desc_enc, prev_vid_enc, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_init_output.append(h_memory)

            self.model_init = Model(input=model_init_input, output=model_init_output)

            # Store inputs and outputs names for model_init
            self.ids_inputs_init = self.ids_inputs
            # first output must be the output probs.
            self.ids_outputs_init = self.ids_outputs + ['preprocessed_input', 'preprocessed_input2',
                                                        'preprocessed_input3', 'next_state']
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_outputs_init.append('next_memory')

            # Second, we need to build an additional model with the capability to have the following inputs:
            #   - preprocessed_input
            #   - preprocessed_input2
            #   - prev_word
            #   - prev_state
            #   - prev_memory (only if using LSTM)
            # and the following outputs:
            #   - softmax probabilities
            #   - next_state
            if params['ENCODER_HIDDEN_SIZE'] > 0:
                if params['BIDIRECTIONAL_ENCODER']:
                    preprocessed_size = params['ENCODER_HIDDEN_SIZE'] * 2 + params['IMG_FEAT_SIZE']
                else:
                    preprocessed_size = params['ENCODER_HIDDEN_SIZE'] + params['IMG_FEAT_SIZE']
            else:
                preprocessed_size = params['IMG_FEAT_SIZE']

            if params['PREV_SENT_ENCODER_HIDDEN_SIZE'] > 0:
                if params['BIDIRECTIONAL_PREV_SENT_ENCODER']:
                    preprocessed_size_prev_desc = params['PREV_SENT_ENCODER_HIDDEN_SIZE'] * 2
                    preprocessed_size_prev_vid = params['PREV_SENT_ENCODER_HIDDEN_SIZE'] * 2
                else:
                    preprocessed_size_prev_desc = params['PREV_SENT_ENCODER_HIDDEN_SIZE']
                    preprocessed_size_prev_vid = params['PREV_SENT_ENCODER_HIDDEN_SIZE']

            # Define inputs
            preprocessed_annotations = Input(name='preprocessed_input',
                                             shape=tuple([None, preprocessed_size]))
            preprocessed_prev_description = Input(name='preprocessed_input2',
                                                  shape=tuple([None, preprocessed_size_prev_desc]))
            preprocessed_prev_video = Input(name='preprocessed_input3',
                                            shape=tuple([None, preprocessed_size_prev_vid]))
            prev_h_state = Input(name='prev_state', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
            input_attentional_decoder = [emb, preprocessed_annotations, preprocessed_prev_description,
                                         preprocessed_prev_video, prev_h_state]

            if params['RNN_TYPE'] == 'LSTM':
                prev_h_memory = Input(name='prev_memory', shape=tuple([params['DECODER_HIDDEN_SIZE']]))
                input_attentional_decoder.append(prev_h_memory)
            # Apply decoder
            rnn_output = sharedAttRNNCond(input_attentional_decoder)
            proj_h = rnn_output[0]
            x_att = rnn_output[1]
            alphas = rnn_output[2]
            prev_desc_att = rnn_output[3]
            prev_desc_alphas = rnn_output[4]
            prev_vid_att = rnn_output[5]
            prev_vid_alphas = rnn_output[6]
            h_state = rnn_output[7]
            if params['RNN_TYPE'] == 'LSTM':
                h_memory = rnn_output[8]
            for reg in shared_reg_proj_h:
                proj_h = reg(proj_h)

            out_layer_mlp = shared_FC_mlp(proj_h)
            out_layer_ctx = shared_FC_ctx(x_att)
            out_layer_ctx = shared_Lambda_Permute(out_layer_ctx)
            out_layer_emb = shared_FC_emb(emb)
            out_layer_prev = shared_FC_prev(prev_desc_att)
            out_layer_prev = shared_Lambda_Permute(out_layer_prev)
            out_layer_prev_vid = shared_FC_prev_vid(prev_vid_att)
            out_layer_prev_vid = shared_Lambda_Permute(out_layer_prev_vid)

            for (reg_out_layer_mlp, reg_out_layer_ctx,
                 reg_out_layer_emb, reg_out_layer_prev,
                 reg_out_layer_prev_vid) in zip(shared_reg_out_layer_mlp,
                                                shared_reg_out_layer_ctx,
                                                shared_reg_out_layer_emb,
                                                shared_reg_out_layer_prev,
                                                shared_reg_out_layer_prev_vid):
                out_layer_mlp = reg_out_layer_mlp(out_layer_mlp)
                out_layer_ctx = reg_out_layer_ctx(out_layer_ctx)
                out_layer_emb = reg_out_layer_emb(out_layer_emb)
                out_layer_prev = reg_out_layer_prev(out_layer_prev)
                out_layer_prev_vid = reg_out_layer_prev_vid(out_layer_prev_vid)

            if params['WEIGHTED_MERGE']:
                additional_output = shared_merge(
                    [out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev, out_layer_prev_vid])
            else:
                additional_output = merge(
                    [out_layer_mlp, out_layer_ctx, out_layer_emb, out_layer_prev, out_layer_prev_vid],
                    mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'],
                    name='additional_input_model_next')
            out_layer = shared_activation_tanh(additional_output)

            for (deep_out_layer, reg_list) in zip(shared_deep_list, shared_reg_deep_list):
                out_layer = deep_out_layer(out_layer)
                for reg in reg_list:
                    out_layer = reg(out_layer)

            # Softmax
            softout = shared_FC_soft(out_layer)
            model_next_inputs = [next_words, preprocessed_annotations, preprocessed_prev_description,
                                 preprocessed_prev_video, prev_h_state]
            model_next_outputs = [softout, preprocessed_annotations, preprocessed_prev_description,
                                  preprocessed_prev_video, h_state]
            if params['RNN_TYPE'] == 'LSTM':
                model_next_inputs.append(prev_h_memory)
                model_next_outputs.append(h_memory)

            self.model_next = Model(input=model_next_inputs, output=model_next_outputs)

            # Store inputs and outputs names for model_next
            # first input must be previous word
            self.ids_inputs_next = [self.ids_inputs[1]] + ['preprocessed_input', 'preprocessed_input2',
                                                           'preprocessed_input3', 'prev_state']
            # first output must be the output probs.
            self.ids_outputs_next = self.ids_outputs + ['preprocessed_input', 'preprocessed_input2',
                                                        'preprocessed_input3', 'next_state']

            # Input -> Output matchings from model_init to model_next and from model_next to model_next
            self.matchings_init_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'preprocessed_input2': 'preprocessed_input2',
                                           'preprocessed_input3': 'preprocessed_input3',
                                           'next_state': 'prev_state'}
            self.matchings_next_to_next = {'preprocessed_input': 'preprocessed_input',
                                           'preprocessed_input2': 'preprocessed_input2',
                                           'preprocessed_input3': 'preprocessed_input3',
                                           'next_state': 'prev_state'}
            if params['RNN_TYPE'] == 'LSTM':
                self.ids_inputs_next.append('prev_memory')
                self.ids_outputs_next.append('next_memory')
                self.matchings_init_to_next['next_memory'] = 'prev_memory'
                self.matchings_next_to_next['next_memory'] = 'prev_memory'

    def VideoTextEmbedding(self, params):
        """
        :param params: config parameters
        :return:
        """

        # Video model
        video = Input(name=self.ids_inputs[0], shape=tuple([None, params['IMG_FEAT_SIZE']]))
        input_video = video
        ##################################################################
        #                       ENCODER
        ##################################################################
        for activation, dimension in params['IMG_EMBEDDING_LAYERS']:
            input_video = TimeDistributed(Dense(dimension, name='%s_1' % activation, activation=activation,
                                                W_regularizer=l2(params['WEIGHT_DECAY'])))(input_video)
            input_video = Regularize(input_video, params, name='%s_1' % activation)

        if params['ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_ENCODER']:
                encoder = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                 W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                 dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                 dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                 return_sequences=False),
                                        name='bidirectional_encoder_' + params['RNN_TYPE'],
                                        merge_mode='concat')(input_video)
            else:
                encoder = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                   W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                   dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                   dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                   return_sequences=False,
                                                   name='encoder_' + params['RNN_TYPE'])(input_video)
            ctx_mean = Lambda(lambda x: K.mean(x, axis=1),
                              output_shape=lambda s: (s[0], s[2]), name='lambda_mean')(input_video)
            input_video = merge([ctx_mean, encoder], mode='concat', concat_axis=-1)
            input_video = Regularize(input_video, params, name='input_video')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_ENCODER']:
                    current_input_video = Bidirectional(eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                                 W_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 U_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 b_regularizer=l2(
                                                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                                                 dropout_W=params[
                                                                                     'RECURRENT_DROPOUT_P'] if params[
                                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                                 dropout_U=params[
                                                                                     'RECURRENT_DROPOUT_P'] if params[
                                                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                                                 return_sequences=False,
                                                                                 ),
                                                        merge_mode='concat',
                                                        name='bidirectional_encoder_' + str(n_layer))(input_video)
                else:
                    current_input_video = eval(params['RNN_TYPE'])(params['ENCODER_HIDDEN_SIZE'],
                                                                   W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                   dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                   dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                       'USE_RECURRENT_DROPOUT'] else None,
                                                                   return_sequences=False,
                                                                   name='encoder_' + str(n_layer))(input_video)

                ctx_mean = Lambda(lambda x: K.mean(x, axis=1),
                                  output_shape=lambda s: (s[0], s[2]), name='lambda_mean')(current_input_video)
                input_video = merge([input_video, ctx_mean], mode='sum')
                input_video = Regularize(input_video, params, name='input_video_' + str(n_layer))

        # Previously generated description from temporally-linked sample
        prev_desc = Input(name=self.ids_inputs[1], batch_shape=tuple([None, None]), dtype='int32')
        # previous description and previously generated words share the same embedding
        shared_emb = Embedding(params['OUTPUT_VOCABULARY_SIZE'],
                               params['TARGET_TEXT_EMBEDDING_SIZE'],
                               name='target_word_embedding',
                               W_regularizer=l2(params['WEIGHT_DECAY']),
                               trainable=self.trg_embedding_weights_trainable,
                               weights=self.trg_embedding_weights,
                               mask_zero=True)
        prev_desc_emb = shared_emb(prev_desc)

        # LSTM for encoding the previous description
        if params['PREV_SENT_ENCODER_HIDDEN_SIZE'] > 0:
            if params['BIDIRECTIONAL_PREV_SENT_ENCODER']:
                prev_desc_enc = Bidirectional(eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                       W_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       U_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       b_regularizer=l2(
                                                                           params['RECURRENT_WEIGHT_DECAY']),
                                                                       dropout_W=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       dropout_U=params['RECURRENT_DROPOUT_P'] if
                                                                       params[
                                                                           'USE_RECURRENT_DROPOUT'] else None,
                                                                       return_sequences=False),
                                              name='prev_desc_emb_bidirectional_encoder_' + params['RNN_TYPE'],
                                              merge_mode='concat')(prev_desc_emb)
            else:
                prev_desc_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                         W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                         dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                             'USE_RECURRENT_DROPOUT'] else None,
                                                         return_sequences=False,
                                                         name='prev_desc_emb_encoder_' + params['RNN_TYPE'])(
                    prev_desc_emb)
            prev_desc_enc = Regularize(prev_desc_enc, params, name='prev_desc_enc')

            # 2.3. Potentially deep encoder
            for n_layer in range(1, params['N_LAYERS_PREV_SENT_ENCODER']):
                if params['BIDIRECTIONAL_DEEP_PREV_SENT_ENCODER']:
                    current_prev_desc_enc = Bidirectional(
                        eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                 W_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 U_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 b_regularizer=l2(
                                                     params['RECURRENT_WEIGHT_DECAY']),
                                                 dropout_W=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 dropout_U=params[
                                                     'RECURRENT_DROPOUT_P'] if params[
                                                     'USE_RECURRENT_DROPOUT'] else None,
                                                 return_sequences=False,
                                                 ),
                        merge_mode='concat',
                        name='prev_desc_emb_bidirectional_encoder_' + str(n_layer))(prev_desc_emb)
                else:
                    current_prev_desc_enc = eval(params['RNN_TYPE'])(params['PREV_SENT_ENCODER_HIDDEN_SIZE'],
                                                                     W_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     U_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     b_regularizer=l2(params['RECURRENT_WEIGHT_DECAY']),
                                                                     dropout_W=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     dropout_U=params['RECURRENT_DROPOUT_P'] if params[
                                                                         'USE_RECURRENT_DROPOUT'] else None,
                                                                     return_sequences=False,
                                                                     name='prev_desc_emb_encoder_' + str(n_layer))(
                        prev_desc_emb)

                current_prev_desc_enc = Regularize(current_prev_desc_enc, params, name='prev_desc_enc_' + str(n_layer))
                prev_desc_enc = merge([prev_desc_enc, current_prev_desc_enc], mode='sum')

        ### FC layers before merge
        input_video = Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                            W_regularizer=l2(params['WEIGHT_DECAY']),
                            activation='linear',
                            name='logit_ctx')(input_video)

        prev_desc_enc = Dense(params['TARGET_TEXT_EMBEDDING_SIZE'],
                              W_regularizer=l2(params['WEIGHT_DECAY']),
                              activation='linear',
                              name='logit_prev')(prev_desc_enc)

        ### Regularization of FC outputs
        input_video = Regularize(input_video, params, name='out_layer_ctx')
        prev_desc_enc = Regularize(prev_desc_enc, params, name='out_layer_prev')

        ### Merge of FC outputs
        if params['WEIGHTED_MERGE']:
            shared_merge = WeightedMerge(mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'],
                                         lambdas_regularizer=l2(params['WEIGHT_DECAY']),
                                         name='merge_inputs')
            additional_output = shared_merge([input_video, prev_desc_enc])
        else:
            additional_output = merge([input_video, prev_desc_enc],
                                      mode=params['ADDITIONAL_OUTPUT_MERGE_MODE'], name='merge_inputs')

        # tanh activation
        shared_activation_tanh = Activation('tanh')
        out_layer = shared_activation_tanh(additional_output)

        ### Final FCs and prediction
        shared_deep_list = []
        shared_reg_deep_list = []
        # 3.6 Optional deep ouput layer
        for i, (activation, dimension) in enumerate(params['DEEP_OUTPUT_LAYERS']):
            if activation.lower() == 'maxout':
                shared_deep_list.append(TimeDistributed(MaxoutDense(dimension,
                                                                    W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name='maxout_%d' % i))
            else:
                shared_deep_list.append(TimeDistributed(Dense(dimension, activation=activation,
                                                              W_regularizer=l2(params['WEIGHT_DECAY'])),
                                                        name=activation + '_%d' % i))
            out_layer = shared_deep_list[-1](out_layer)
            [out_layer, shared_reg_out_layer] = Regularize(out_layer,
                                                           params, shared_layers=True,
                                                           name='out_layer' + str(activation))
            shared_reg_deep_list.append(shared_reg_out_layer)

        # 3.7. Output layer: Softmax
        shared_FC_soft = Dense(2,
                               activation=params['CLASSIFIER_ACTIVATION'],
                               W_regularizer=l2(params['WEIGHT_DECAY']),
                               name=self.ids_outputs[0])
        softout = shared_FC_soft(out_layer)

        self.model = Model(input=[video, prev_desc], output=softout)
