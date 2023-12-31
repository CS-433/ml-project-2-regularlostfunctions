"""
    Script for training recurrent neural network models to perform
    the detection of Epilepsy Seizures on a EEG signal. This task is part of the
    Use Case 13 of DeepHealth project.

    This script uses Keras toolkit to create and train the neural networks.

    Authors:
        DeepHealth team @ PRHLT, UPV
"""


import os
import sys
import argparse
from datetime import datetime
from tqdm import tqdm
import numpy
import matplotlib.pyplot as plt

from data_utils_detection import RawRecurrentDataGenerator
from models_keras import create_model

import tensorflow as tf
from tensorflow import keras
import tensorflow.keras.backend as K
from tensorflow.keras.optimizers import Adam, SGD
from sklearn.metrics import confusion_matrix, classification_report, f1_score



def main(args):
    index_training = [args.index]
    index_validation = [args.index_val]
    patient_id = args.id
    model_id = args.model
    epochs = args.epochs
    batch_size = args.batch_size
    initial_lr = args.lr
    opt = args.opt
    resume_dir = args.resume
    starting_epoch = args.starting_epoch

    # Set GPU
    os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu


    # Create experiment directory or use an existing one to resume training

    if resume_dir is not None:
        # Resume training
        exp_dir = resume_dir
        model_dir = os.path.join(exp_dir, 'models')
        model_filename = None

        for f in os.listdir(model_dir):
            if 'last' in f:
                model_filename = os.path.join(model_dir, f)
        #
        if model_filename is None:
            raise Exception(f'Last model not found in {model_dir}')
        #
    else:
        # Create dir for the experiment
        os.makedirs('keras_experiments', exist_ok=True)

        exp_dir = os.path.join('keras_experiments' ,
                f'detection_recurrent_{patient_id}_{model_id}_{opt}_{initial_lr}')

        exp_time = datetime.now().strftime("%d-%b_%H:%M")
        exp_dir = f'{exp_dir}_{exp_time}'
        os.makedirs(exp_dir)

        ## Create dir to store models
        model_dir = os.path.join(exp_dir, 'models')
        os.makedirs(model_dir)
    #


    # Create data generator objects

    # Data Generator Object for training
    print('\n\nCreating Training Data Generator...', file=sys.stderr)
    dg = RawRecurrentDataGenerator(index_filenames=index_training,
                          window_length=args.window_length, # in seconds
                          shift=args.shift, # in seconds
                          timesteps=args.timesteps, # in seconds
                          sampling_rate=256, # in Hz
                          batch_size=batch_size,
                          in_training_mode=True,
                          balance_batches=True,
                          patient_id=patient_id)
    #


    segments                = 10 # Number of CV segments
    max_segments_in_history = 3
    batches_per_segm        = int(len(dg)/segments)

    initial_segments = max_segments_in_history*(max_segments_in_history+1)/2 # Number of segments that will be computed during the initial stage
    regime_segments = (segments - max_segments_in_history -1)*max_segments_in_history # Number of segments that will be computed during the rest
    validation_segments = segments -1 # Number of segments that will be run for validation (approximated, as the time is not the same)
    batch_time = 2.5
    segment_time = batches_per_segm * batch_time
    print(f'\nEstimated Total Training time time: {segment_time*(initial_segments+regime_segments+validation_segments)/3600:02f} hours\n', file=sys.stderr)

    # Get input shape
    x, y = dg[0]
    input_shape = x.shape[1:-1]

    # Create or Load the model

    if resume_dir is None:
        # Create model and define optimizer
        model = create_model(model_id, input_shape, 2)

        if opt == 'adam':
            optimizer = Adam(learning_rate=initial_lr)
        elif opt == 'sgd':
            optimizer = SGD(learning_rate=initial_lr)
        else:
            raise Exception(f'Wrong optimizer name, check help with -h.')


        model.compile(optimizer=optimizer,
                    loss='categorical_crossentropy',
                    metrics=['accuracy']
                    )

    else:
        # Load model, already compiled and with the optimizer state preserved
        model = keras.models.load_model(model_filename)

    model.summary()

    # Log files
    log_filename = f'{exp_dir}/training.log'
    logger = open(log_filename, 'a')
    logger.write('segment, train_acc, train_loss, val_acc, '
                + 'val_loss, val_f1score, val_acc_combined_channels, val_f1score_combined_channels\n')

    logger.flush()


    best_val_score = 0.0
    seg_scores = []
    acc = 0
    fsc = 0
    fsc_i = 0


    # Train the model
    for seg in range(segments):

        print(f'\nTraining segment {seg}/{segments-1}...', file=sys.stderr)
        print(f'\nNO DATA SHUFFLING!!!!', file=sys.stderr)
        #RLF############################################################################################
        ############# dg.shuffle_data()



        first_segment_of_block = max(0, seg - max_segments_in_history)*batches_per_segm
        last_segment_of_block = (seg+1)*batches_per_segm
        print(f'\nSegments: {max(0, seg - max_segments_in_history)}({seg}-{max_segments_in_history}) - {seg+1}\n', file=sys.stderr)
        print(f'\nBatches in these segments: {first_segment_of_block} - {last_segment_of_block}\n', file=sys.stderr)
        print(f'\nEstimated time: {2.5*(last_segment_of_block-first_segment_of_block)/3600:02f} hours\n', file=sys.stderr)

        # Set a progress bar for the training loop
        pbar = tqdm(range(first_segment_of_block, last_segment_of_block))

        for i in pbar:
            # Load batch of data
            x, y = dg[ seg*batches_per_segm + i]

            y = keras.utils.to_categorical(y, num_classes=2)

            for channel in range(x.shape[3]):
                x_channel = x[:, :, :, channel]

                # Forward and backward of the channel through the net
                outputs = model.train_on_batch(x_channel, y=y, reset_metrics=False)

            pbar.set_description(f'Training[loss={outputs[0]:.5f}, acc={outputs[1]:.5f}]')
            #

            #RLF############################################################################################
            ########### THESE ARE ONLY THE RESULTS OF THE LAST CHANNEL!

            # Store training results
            train_loss = outputs[0]
            train_acc = outputs[1]


        if segments > 1:
            # Validation
            print(f'\nValidation with segment {seg+1}...', file=sys.stderr)

            Y_true_single_channel = list()
            Y_pred_single_channel = list()
            Y_true = list()
            Y_pred = list()

            accumulated_loss = 0.0

            for j in tqdm(range(batches_per_segm)):
                x, y = dg[ last_segment_of_block + j ]

                y = keras.utils.to_categorical(y, num_classes=2)

                channels_y_pred = list()
                for channel in range(x.shape[3]):
                    x_channel = x[:, :, :, channel]

                    # Forward and backward of the channel through the net
                    y_pred = model.predict(x_channel)

                    accumulated_loss += keras.losses.CategoricalCrossentropy()(y, y_pred)

                    channels_y_pred.append(y_pred)
                    Y_pred_single_channel += y_pred.argmax(axis=1).tolist()
                    Y_true_single_channel += y.argmax(axis=1).tolist()
                #
                channels_y_pred = numpy.array(channels_y_pred)
                # (23, batch_size, 2)
                channels_y_pred = numpy.sum(channels_y_pred, axis=0)
                channels_y_pred = channels_y_pred / 23.0
                # print(channels_y_pred.shape) -> (batch_size, 2)

                Y_true += y.argmax(axis=1).tolist()
                Y_pred += channels_y_pred.argmax(axis=1).tolist()
            #

            y_true = numpy.array(Y_true) * 1.0
            y_pred = numpy.array(Y_pred) * 1.0
            y_true_single_channel = numpy.array(Y_true_single_channel) * 1.0
            y_pred_single_channel = numpy.array(Y_pred_single_channel) * 1.0

            # Calculate validation loss
            val_loss = accumulated_loss / len(dg)

            # Calculate other metrics
            val_accuracy_single_channel = sum(y_true_single_channel == y_pred_single_channel) / len(y_true_single_channel)
            cnf_matrix = confusion_matrix(y_true_single_channel, y_pred_single_channel)
            report = classification_report(y_true_single_channel, y_pred_single_channel)
            fscore_single_channel = f1_score(y_true_single_channel, y_pred_single_channel, labels=[0, 1], average='macro')


            print('***************************************************************\n', file=sys.stderr)
            print(f'Segment {seg}: Validation results\n', file=sys.stderr)
            print(' -- Single channel results (no combination of channels) --\n', file=sys.stderr)
            print(f'Validation acc : {val_accuracy_single_channel}', file=sys.stderr)
            print(f'Validation macro f1-score : {fscore_single_channel}', file=sys.stderr)
            print('Confussion matrix:', file=sys.stderr)
            print(f'{cnf_matrix}\n', file=sys.stderr)
            print('Classification report:', file=sys.stderr)
            print(report, file=sys.stderr)

            print('\n--------------------------------------------------------------\n', file=sys.stderr)

            val_accuracy = sum(y_true == y_pred) / len(y_true)
            cnf_matrix = confusion_matrix(y_true, y_pred)
            report = classification_report(y_true, y_pred)
            fscore = f1_score(y_true, y_pred, labels=[0, 1], average='macro')
            fscore_i = f1_score(y_true, y_pred, labels=[1, 0], average='macro')

            print(' -- All channels involved (combined for each timestamp) --\n', file=sys.stderr)
            print(f'Validation acc : {val_accuracy}', file=sys.stderr)
            print(f'Validation macro f1-score : {fscore}', file=sys.stderr)
            print('Confussion matrix:', file=sys.stderr)
            print(f'{cnf_matrix}\n', file=sys.stderr)
            print('Classification report:', file=sys.stderr)
            print(report, file=sys.stderr)
            print('***************************************************************\n\n', file=sys.stderr)


            acc += val_accuracy
            fsc += fscore
            fsc_i += fscore_i

            seg_scores.append( [(val_accuracy,cnf_matrix, report, fscore, fscore_i) ] )

            logger.write('%d,%g,%g,%g,%g,%g,%g,%g\n' % (seg, train_acc, train_loss,
                val_accuracy_single_channel, val_loss, fscore_single_channel,
                val_accuracy, fscore))

            logger.flush()


            if val_accuracy > best_val_score:
                # Save best model if score is improved
                best_val_score = val_accuracy
                model.save(f'{model_dir}/{model_id}_best_epoch' + f'_{seg:04d}_{val_accuracy:.4f}.h5')

        # Save last model
        model.save(f'{model_dir}/{model_id}_seg{seg}.h5')

    print("#################################################################\n", file=sys.stderr)


    acc         /= (segments -1)
    fsc         /= (segments -1)
    fsc_i       /= (segments -1)


    print(f"Accuracy:\t{acc*100:02f}%\n",file=sys.stderr)
    print(f"F1 score:\t{fsc:04f}\n",file=sys.stderr)
    print(f"F1i score:\t{fsc_i:04f}\n",file=sys.stderr)

    print("#################################################################\n", file=sys.stderr)
    print(seg_scores, file=sys.stderr)





# ------------------------------------------------------------------------------

if __name__ == '__main__':

    # Get arguments
    parser = argparse.ArgumentParser(description='Script for training models' +
        ' to detect Epilepsy Seizures.')

    parser.add_argument('--index', help='Index of recordings to use for training. ' +
                        'Example: "../indexes_detection/chb01/train.txt"')

    parser.add_argument('--index-val', help='Index of recordings to use for validation. ' +
                        'Example: "../indexes_detection/chb01/validation.txt"')

    parser.add_argument('--id', help='Id of the patient, e.g. "chb01".', required=True)

    parser.add_argument('--model', help='Model id to use: "lstm", "gru".',
                         default='lstm')

    parser.add_argument('--epochs', type=int, help='Number of epochs to' +
         ' perform.', default=1)

    parser.add_argument('--batch-size', type=int, help='Batch size.',
        default=64)

    parser.add_argument('--lr', type=float, help='Initial learning rate. Default -> 0.0001',
        default=0.0001)

    parser.add_argument('--opt', help='Optimizer: "adam", "sgd". Default -> adam',
        default='adam')

    parser.add_argument('--gpu', help='Id of the gpu to use.'+
        ' Usage --gpu 0', default='0')


    # Arguments of the data generator
    parser.add_argument('--window-length', type=float, help='Window length '
    + ' in seconds. Default -> 1', default=1)

    parser.add_argument('--shift', type=float, help='Window shift '
    + ' in seconds. Default -> 0.5', default=0.5)

    parser.add_argument('--timesteps', type=int, help='Timesteps to use as a '
    + ' sequence. Default -> 19', default=19)



    # Arguments to resume an experiment
    parser.add_argument('--resume', help='Directory of the experiment dir to resume.',
                default=None)

    parser.add_argument('--starting-epoch', help='Number of the epoch to start ' +
                        'the training again. (--epochs must be the total ' +
                        'number of epochs to be done, including the epochs ' +
                        'already done before resuming)', type=int, default=0)


    main(parser.parse_args())