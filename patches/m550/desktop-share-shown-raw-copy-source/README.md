# Reuse the raw-source snapshot when copying it

The source view shares its displayed string with Copy instead of making it again. Fancy rendering still defers preparing source until Copy is clicked.

Ten native fixture shapes matched displayed/copied bytes, including copying a previous frame after replacement. A raw 2 MiB source's preparation peak fell from 4 to 2 MiB; preparing the Copy payload reused the existing buffer. The system clipboard and app RAM were not measured.
