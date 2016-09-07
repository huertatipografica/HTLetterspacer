<section id="download" data-magellan-target="download">
  <div class="row">
    <div class="small-12 columns">

      <div class="orbit" role="region" aria-label="Favorite Space Pictures" data-orbit>
        <ul class="orbit-container">
          <button class="orbit-previous"><span class="show-for-sr">Previous Slide</span>&#9664;&#xFE0E;</button>
          <button class="orbit-next"><span class="show-for-sr">Next Slide</span>&#9654;&#xFE0E;</button>

          <?php
          $quotes = [
              [
              'cite' => 'An amazing tool to have a well-done spacing in every step of a font project',
              'author' => 'Eduardo Tunni',
              ],
              [
              'cite' => 'It was very useful for defining Henderson. We made different spacings very quickly to decide the better one',
              'author' => 'Alejandro Paul',
              ],
              [
              'cite' => 'It works great',
              'author' => 'Pablo Impallari',
              ],
            ];
          ?>

          <?php foreach ($quotes as $q): ?>
            <li class="is-active orbit-slide">
              <div class="row">
                <div class="large-7 large-offset-3 medium-8 medium-offset-2  columns">
                 <p>
                  <img src="/images/q.png">
                  <?php echo $q['cite'] ?>
                  <span>– <?php echo $q['author'] ?></span>
                </p>
              </div>
            </div>
          </li>
        <?php endforeach ?>

      </ul>
    </div>


    <div class="medium-9 medium-offset-3  columns">
      <a href="#" class="button "><i class="fa fa-download"></i> Download</a>
      <a href="#" class="button secondary"><i class="fa fa-github"></i> Contribute</a>
    </div>
  </div>
</div>
</section>