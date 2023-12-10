# Recurrent raw signal experiments

mkdir -p log/
#for patient in  "chb05" "chb06" "chb08" "chb12" "chb14" "chb15" "chb24" "chb01" "chb03"
for patient in  "chb01"
do
	touch log/${patient}_recurrent.out
	touch log/${patient}_recurrent.err

	#python python/train_recurrent_keras.py --index ../indexes_detection/$patient/train.txt --index-val ../indexes_detection/$patient/validation.txt --id $patient --model gru --epochs 10 --batch-size 64 --gpus 1 >log/${patient}_recurrent.out 2>log/${patient}_recurrent.err
	python ../python/train_recurrent_keras.py --index ../../indexes_detection/$patient/train.txt\
	--index-val ../../indexes_detection/$patient/validation.txt --id $patient --model gru\
	--epochs 10 --batch-size 64\
	>log/${patient}_recurrent.out 2>log/${patient}_recurrent.err
done
