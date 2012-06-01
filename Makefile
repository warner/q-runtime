
create:
	./bin/ssp create-node c1
	./bin/ssp create-node c2
	./bin/ssp start c1
	./bin/ssp start c2
	./bin/ssp gossip c1 c2

destroy:
	./bin/ssp stop c1
	./bin/ssp stop c2
	rm -rf c1 c2
