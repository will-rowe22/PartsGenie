pip install pandas
pip install synbiochem-py

export PYTHONPATH=$PYTHONPATH:.

python \
	scripts/plasmid_writer.py \
	scripts/plasmid_writer_in.csv \
	scripts/plasmid_writer_out.csv \
	https://ice.synbiochem.co.uk \
	USERNAME \
	PASSWORD \
	synbiochem \