import chainer
import chainer.links as L
import chainer.functions as F
from chainer import cuda,Chain,optimizers,serializers
import numpy as np
import os
import argparse
import pylab
from model import Generator, Discriminator, VGG
from prepare import prepare_dataset

xp=cuda.cupy
cuda.get_device(0).use()

def set_optimizer(model,alpha=0.0002,beta=0.5):
    optimizer = optimizers.Adam(alpha=alpha,beta1=beta)
    optimizer.setup(model)

    return optimizer

def calc_vgg_loss(feat1, feat2):
    _,_,h,w=feat1.shape

    return F.mean_squared_error(feat1,feat2)/(h*w)

parser=argparse.ArgumentParser(description="ESRGAN")
parser.add_argument("--epoch",default=1000,type=int,help="the number of epochs")
parser.add_argument("--batchsize",default=2,type=int,help="batchsize")
parser.add_argument("--testsize",default=2,type=int,help="testsize")
parser.add_argument("--aw",default=0.005,type=float,help="weight of adversarial loss")
parser.add_argument("--l1",default=0.01,type=float,help="weight of l1 loss")
parser.add_argument("--interval",default=1,type=int,help="interval of snapshot")
parser.add_argument("--Ntrain",default=24000,type=int,help="the number of training images")
parser.add_argument("--iterations",default=2000,type=int,help="the numbef of iterations")

args = parser.parse_args()
epochs=args.epoch
batchsize=args.batchsize
testsize=args.testsize
adver_weight=args.aw
l1_weight=args.l1
interval=args.interval
Ntrain=args.Ntrain
iterations=args.iterations

image_path="/coco/"
image_list=os.listdir(image_path)

outdir="./output_pretrain"
if not os.path.exists(outdir):
    os.mkdir(outdir)

test_box=[]
for i in range(testsize):
    rnd = np.random.randint(Ntrain + 1, Ntrain + 100)
    image_name = image_path + image_list[rnd]
    _, sr = prepare_dataset(image_name)
    test_box.append(sr)

x_test=chainer.as_variable(xp.array(test_box).astype(xp.float32))

generator=Generator()
generator.to_gpu()
gen_opt=set_optimizer(generator)

for epoch in range(epochs):
    sum_gen_loss=0
    sum_dis_loss=0
    for batch in range(0,iterations,batchsize):
        hr_box=[]
        sr_box=[]
        for index in range(batchsize):
            rnd = np.random.randint(Ntrain)
            image_name = image_path + image_list[rnd]
            hr, sr = prepare_dataset(image_name)
            hr_box.append(hr)
            sr_box.append(sr)

        x=chainer.as_variable(xp.array(sr_box).astype(xp.float32))
        t=chainer.as_variable(xp.array(hr_box).astype(xp.float32))
        
        y=generator(x)
        l1_loss=F.mean_absolute_error(y,t)

        gen_loss=l1_weight*l1_loss

        generator.cleargrads()
        gen_loss.backward()
        gen_opt.update()
        gen_loss.unchain_backward()

        sum_gen_loss+=gen_loss.data.get()

        if epoch%interval==0 and batch==0:
            serializers.save_npz("%s/generator_pretrain.model"%(outdir),generator)
            with chainer.using_config("train", False):
                y = generator(x_test)
            y = y.data.get()
            sr = x_test.data.get()
            for i_ in range(testsize):
                tmp = (np.clip((sr[i_,:,:,:])*127.5 + 127.5, 0, 255)).transpose(1,2,0).astype(np.uint8)
                pylab.subplot(testsize,2,2*i_+1)
                pylab.imshow(tmp)
                pylab.axis('off')
                pylab.savefig('%s/visualize_%d.png'%(outdir, epoch))
                tmp = (np.clip((y[i_,:,:,:])*127.5 + 127.5, 0, 255)).transpose(1,2,0).astype(np.uint8)
                pylab.subplot(testsize,2,2*i_+2)
                pylab.imshow(tmp)
                pylab.axis('off')
                pylab.savefig('%s/visualize_%d.png'%(outdir, epoch))

    print("epoch:{}".format(epoch))
    print("Discrimintor loss:{}".format(sum_dis_loss/Ntrain))
    print("Generator loss:{}".format(sum_gen_loss/Ntrain))