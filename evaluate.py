import os#sup
import glob
from random import shuffle

import numpy as np
import h5py

from keras.models import load_model

import matplotlib.pyplot as plt
from skimage.filters import gaussian

from dataset_processing.grasp import BoundingBoxes, detect_grasps
import datagen

# Networks to test.
#NETWORK = 'data/networks/19*/'  # evaluate just one epoch
NETWORK = 'data/networks/*/'  # glob synatx to output network folders.
EPOCH = None  # Specify epoch or None to test all.

#RAW_DATA_DIR = 'data/cornell'

WRITE_LOG = True
LOGFILE = 'evaluation_output.txt'

NO_GRASPS = 1  # Number of local maxima to check against ground truth grasps.
VISUALISE_FAILURES = False
VISUALISE_SUCCESSES = False
SAVE_OUTPUT = False

#_pos_grasp_pattern = os.path.join(RAW_DATA_DIR, 'pcd%04dcpos.txt')


def write_log(s):
    if WRITE_LOG:
        with open(LOGFILE, 'a') as f:
            f.write(s)


def plot_output(rgb_img, depth_img, grasp_position_img, grasp_angle_img, ground_truth_bbs, no_grasps=1, grasp_width_img=None, file_name=None):
        """
        Visualise the outputs.
        """
        grasp_position_img = gaussian(grasp_position_img, 5.0, preserve_range=True)

        if grasp_width_img is not None:
            grasp_width_img = gaussian(grasp_width_img, 1.0, preserve_range=True)

        gt_bbs = BoundingBoxes.load_from_array(ground_truth_bbs)
        gs = detect_grasps(grasp_position_img, grasp_angle_img, width_img=grasp_width_img, no_grasps=no_grasps, ang_threshold=0)

        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(2, 2, 1)
        ax.imshow(rgb_img)
        for g in gs:
            g.plot(ax)

        for g in gs:
            g.plot(ax, color='r')
        #for g in gt_bbs:
        #    g.plot(ax, color='g')

        ax = fig.add_subplot(2, 2, 2)

        ax.imshow(depth_img.squeeze())
        for g in gs:
            g.plot(ax, color='r')

        for g in gt_bbs:
            g.plot(ax, color='g')

        ax = fig.add_subplot(2, 2, 3)
        im = ax.imshow(grasp_position_img, cmap='Reds')#, vmin=0, vmax=1)
        fig.colorbar(im, ax=ax)

        ax = fig.add_subplot(2, 2, 4)
        plot = ax.imshow(grasp_angle_img, cmap='hsv', vmin=-np.pi / 2, vmax=np.pi / 2)
        plt.colorbar(plot)

        if file_name is not None:
            plt.savefig(file_name)
        else:
            plt.show()


def calculate_iou_matches(grasp_positions_out, grasp_angles_out, ground_truth_bbs, no_grasps=1, grasp_width_out=None, min_iou=0.25):
    """
    Calculate a success score using the (by default) 25% IOU metric.
    Note that these results don't really reflect real-world performance.
    """
    succeeded = []
    failed = []
    for i in range(grasp_positions_out.shape[0]):
        grasp_position = grasp_positions_out[i, ].squeeze()
        grasp_angle = grasp_angles_out[i, :, :].squeeze()

        grasp_position = gaussian(grasp_position, 5.0, preserve_range=True)

        if grasp_width_out is not None:
            grasp_width = grasp_width_out[i].squeeze()
            grasp_width = gaussian(grasp_width, 1.0, preserve_range=True)
        else:
            grasp_width = None

        gt_bbs = BoundingBoxes.load_from_array(ground_truth_bbs[i].squeeze())
        #gt_bbs = ground_truth_bbs

        gs = detect_grasps(grasp_position, grasp_angle, width_img=grasp_width, no_grasps=no_grasps, ang_threshold=0)
        for g in gs:
            if g.max_iou(gt_bbs) > min_iou:
                succeeded.append(i)
                break
        else:
            failed.append(i)

    return succeeded, failed


def run():
    global NO_GRASPS, VISUALISE_FAILURES, VISUALISE_SUCCESSES

    # Load the dataset data.
    model_folders = glob.glob(NETWORK)
    model_folders.sort()

    for model_folder in model_folders:

        print('Evaluating:  %s, epoch %s' % (model_folder, EPOCH))

        write_log('\n')
        write_log(model_folder.split('/')[-1])
        write_log('\t')

        epochs = [EPOCH]
        if EPOCH is None:
            # Get all of them
            saved_models = glob.glob(os.path.join(model_folder, 'epoch_*_model.hdf5'))
            saved_models.sort()
            #print "All epoch models"
            #print saved_models
            epochs = [int(s[-13:-11]) for s in saved_models]
        else:
            epochs = EPOCH

        for epoch in epochs:
            # Load the output data.
            model_output_fn = os.path.join(model_folder, 'epoch_%02d_val_output.npz' % epoch)

            # Load the model and compute the output.
            print('No pre-computed values.  Computing now.')
            model_checkpoint_fn = os.path.join(model_folder, 'epoch_%02d_model.hdf5' % epoch)
            model = load_model(model_checkpoint_fn)

            gen = datagen.DataGenerator(batch_size = 500, train=False)

            totalSuc = 0
            totalFail = 0

            write_log('Epoch no %d ' % epoch)

            for batchNum in range(len(gen)):
                depth_imgs, rgb_imgs, bbs_all = gen.getTest(batchNum)

                model_output_data = model.predict(depth_imgs)
                grasp_positions_out = model_output_data[0]

                '''for i in range(500):

                    fig = plt.figure(figsize=(10, 10))
                    ax = fig.add_subplot(2, 2, 1)
                    im = ax.imshow(grasp_positions_out[i, :, :, 0])
                    fig.colorbar(im, ax=ax)

                    ax = fig.add_subplot(2, 2, 2)
                    im = ax.imshow(grasp_positions_out[i, :, :, 1])
                    fig.colorbar(im, ax=ax)

                    ax = fig.add_subplot(2, 2, 3)
                    ax.imshow(rgb_imgs[i, ])

                    ax = fig.add_subplot(2, 2, 4)
                    im = ax.imshow(grasp_positions_out[i, :, :, 0])# - grasp_positions_out[i, :, :, 1])
                    fig.colorbar(im, ax=ax)
                    plt.show()

                continue'''
                if grasp_positions_out.shape[1] > 10000:#we're using a classification output that must be reshaped
                    grasp_positions_out = grasp_positions_out.reshape((-1, 300, 300, 2))
                    grasp_positions_out = grasp_positions_out[:, :, :, 0]# - grasp_positions_out[:, :, :, 1]

                grasp_angles_out = np.arctan2(model_output_data[2], model_output_data[1])/2.0
                grasp_width_out = model_output_data[3] * 150.0

                # IOU TESTING.
                succeeded, failed = calculate_iou_matches(grasp_positions_out, grasp_angles_out, bbs_all, no_grasps=NO_GRASPS, grasp_width_out=grasp_width_out)

                s = len(succeeded) * 1.0
                totalSuc += s
                f = len(failed) * 1.0
                totalFail += f
                print('%s\t%s\t%s/%s\t%0.02f%s' % (model_folder.split('/')[-1], epoch, s, s+f, s/(s+f)*100.0, '%'))
                print('%f %f %f', totalSuc / (totalSuc + totalFail), totalSuc, totalSuc + totalFail)
                write_log('%0.02f\t' % (s/(s+f)*100.0))

                if VISUALISE_FAILURES:
                    print('Plotting Failures')
                    shuffle(failed)
                    for i in failed:
                        file_name = None
                        if SAVE_OUTPUT:
                            file_name = "visualize/fail" + str(i) + ".png"
                        plot_output(rgb_imgs[i, ], depth_imgs[i, ], grasp_positions_out[i, ].squeeze(), grasp_angles_out[i, ].squeeze(), bbs_all[i],
                                    no_grasps=NO_GRASPS, grasp_width_img=grasp_width_out[i, ].squeeze(), file_name=file_name)

                if VISUALISE_SUCCESSES:
                    print('Plotting Successes')
                    shuffle(succeeded)
                    for i in succeeded:
                        file_name = None
                        if SAVE_OUTPUT:
                            file_name = "visualize/succ" + str(i) + ".png"
                        plot_output(rgb_imgs[i, ], depth_imgs[i, ], grasp_positions_out[i, ].squeeze(), grasp_angles_out[i, ].squeeze(), bbs_all[i],
                                    no_grasps=NO_GRASPS, grasp_width_img=grasp_width_out[i, ].squeeze(), file_name=file_name)
            write_log('Final epoch %d perf, %0.02f, %d %d\n' % (epoch, totalSuc / (totalSuc + totalFail), totalSuc, totalFail + totalSuc))

if __name__ == '__main__':
    run()
