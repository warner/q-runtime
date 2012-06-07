
create:
	./bin/qrt create-node c1
	./bin/qrt create-node c2
	./bin/qrt start c1
	./bin/qrt start c2
	./bin/qrt gossip c1 c2

destroy:
	-./bin/qrt stop c1
	-./bin/qrt stop c2
	rm -rf c1 c2
