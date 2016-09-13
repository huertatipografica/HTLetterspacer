  <section id="start" data-magellan-target="start">
  	<div class="row">
  		<div class="medium-8 medium-offset-3 columns">

  			<h2>Get started</h2>
  			<ul class="accordion" data-accordion data-allow-all-closed="true">

  				<li class="accordion-item is-active" data-accordion-item>
  					<a href="#" class="accordion-title">
  						<h5>
                <span class=" badge">1</span>
                What do I need to set up to use it?
              </h5>
            </a>
            <div class="accordion-content" data-tab-content>
              <p>For using the script you need two main things:</p>
              <ol>
               <li>
                <p>Declare custom parameters on each master of your Glyphs file or a general default one in the script code. </p>
              </li>
              <li>
                <p>A configuration file in the same folder than your Glyphs file, named like <code>yourfontname_autospace.py</code>, with all the glyph categories, they area value and glyph of reference to define the vertical range where the group will be measured. If there is no file in the same folder, or with incompatible name, you will get an error.</p>
              </li>
            </ol>
          </div>
        </li>

        <li class="accordion-item" data-accordion-item>
         <a href="#" class="accordion-title">
          <h5>
            <span class=" badge">2</span>
            Parameters
          </h5>
        </a>
        <div class="accordion-content" data-tab-content>
          <p>Parameters are declared in the custom master parameters field, in the font info, for each of the masters you want to store the values.</p>
          <a href="/images/params.png" target="_blank"><img src="/images/params.png" alt="Diagram of depth" style='border:1px solid #ccc; margin-bottom:10px'></a>


          <p>If the master doesn't have the appropriate custom parameters or the parameter name is different as required, the script will use the default values on the source code. Check example files to see it configured.</p>
          <p>Once the script is executed it will output the results in the macro window, telling you if it is using the custom parameters or default parameters. </p>

          <h3>Parameter 1: paramArea</h3>
           <p>The <code>paramArea</code> parameter lets you define how much area (measured in thousand units) do you want between the lowercase letters inside the x-height. A font suitable for text at 1000 UPM typically uses a value between 200 and 400.</p>

        
           <a href="/images/README-01.png" target="_blank"><img src="/images/README-01.png" alt="Diagram of depth"></a>


           <a href="/images/README-02.png" target="_blank"><img src="/images/README-02.png" alt="Diagram of area parameter compensation on left of C"></a>


           <a href="/images/README-03.png" target="_blank"><img src="/images/README-03.png" alt="Diagram of area parameter compensation on left of N"></a>




           <a href="/images/README-06.png" target="_blank"><img src="/images/README-06.png" alt="Diagram of depth parameter variations 10 and 20"></a>
           <h3>Parameter 2: paramDepth</h3>
         <p>The <code>paramDepth</code> parameter (measured relatively as a % of x-height) lets you define how deep into open counterforms you want to measure the space, from the extreme points of each glyphs to its center. This parameter will affect rounded or open shapes. For example: a square with x-height has no depth, its side is vertical, and this value won't affect it. </p>
           <a href="/images/README-04.png" target="_blank"><img src="/images/README-04.png" alt="Diagram of area parameter compensation on right of C"></a>

            <a href="/images/README-05.png" target="_blank"><img src="/images/README-05.png" alt="Diagram of depth parameter variations 10 20 and 25"></a>

           <a href="/images/README-07.png" target="_blank"><img src="/images/README-07.png" alt="Diagram of depth parameter not effecting flat sides"></a>

         <p>But a triangle with x-height (a circle, a c-shape or a T) has a long distance and amount of white from its extreme points or sides to the center of the letter. Our eyes doesn't pay attention to the whole area, so the program doesn't do it either. But you need to decide how much of this "big white" you want to measure setting up this parameter.</p>
         <p>Depending on the design, this value moves between 10 or 25 (percent of x-height).</p>
         
         <h3>Parameter 3: paramOvershoot</h3>
         <p>The <code>paramOvershoot</code> parameter expands the vertical range or height where you measure the space, above and below the shape, by a certain % of x-height. It allows you to make slight differences when a sign has outlines exceeding the height on its group of letters, typically ascenders or descenders. For example: in a sans serif font, a dotless /i/ and and /l/ could have exactly the same shape between the baseline and x-height line. Setting up an overshot will expand the range up and down and will result in a different calculation of space for each sign. In this case, the sign with ascenders (the /l/) will result on a looser space, and its difference depends on how much the overshot is.</p>
         <p>This parameter is optional and depends on what do you want to do with it, but is intended to be used similar to an overshot</p>
       </div>
     </li>

     <li class="accordion-item" data-accordion-item>
       <a href="#" class="accordion-title">
        <h5>
          <span class=" badge">3</span>
          Configuration file
        </h5>
      </a>
      <div class="accordion-content" data-tab-content>
        <p>A <a href="#examples">text file</a> in the same Glyphs file folder will define all the different alterations for each category of signs, as well as a reference sign which defines the height or vertical range of the signs group. For example: lowercase vertical range could be defined with <code>x</code>, uppercase with <code>X</code> or <code>H</code>, small caps with <code>x.sc</code>, numbers with <code>one</code>, etc.</p>
        <h5>Config values and rules</h5>
        <p>Each line of the configuration files will contain a set of rules to apply to a group of glyphs. Lines should be ordered from general to specific rules. Each field in this line should be separated by comma, with a trailing comma:</p>
        <pre><code>Script, Category, Subcategory, value, reference glyph, name filter,</code></pre>
        <hr>
        <table>
         <thead>
          <tr>
           <th>Item</th>
           <th>Description</th>
         </tr>
       </thead>
       <tbody>
        <tr>
         <td>Script</td>
         <td>The name of the script type. Asterisk <code>*</code> means all</td>
       </tr>
       <tr>
         <td>Category</td>
         <td>The name of the Glyph category. For the lowercase glyphs is Letter</td>
       </tr>
       <tr>
         <td>Subcategory</td>
         <td>The name of the Glyph subcategory. For the lowercase glyphs is Lowercase</td>
       </tr>
       <tr>
         <td>Value</td>
         <td>The number or coefficient of variation that changes the area parameter in each category or rule. In this case the area parameter will be maintained multiplied by 1. If you set up a paramArea of 400 and this value is equal to 2, it means that the area applied will be 800. In this version of script only area parameter is altered by this number.</td>
       </tr>
       <tr>
         <td>Reference glyph</td>
         <td>It's the name of the glyph that defines the vertical range or area where spacing will be measured. For lowercase we will use the <code>x</code>, but you can use any other glyph with the same height, lower and higher points. (Note: it seems silly to define this if we have values as x-height or caps height on the font. But it is made in this way to make it open to any other group of glyphs without standard values on the font, like small caps, numbers, superscript, devanagari, etc.)</td>
       </tr>
       <tr>
         <td>Filter</td>
         <td>You can filter the rules by any suffix or part of the glyph name. <code>*</code> means <code>all</code>. But, for example, you can constrain the rule just to the ordinal glyphs writing <code>ord</code> in this rule. So it will be applied to <code>ordfeminine</code>, <code>ordmasculine</code> and <code>mordor</code>, if you have this last one.</td>
       </tr>
     </tbody>
   </table>
   <p>A simple example of the first 4 lines of a config file for a given font:</p>
   <pre><code>*,Letter,Uppercase,1.5,H,*,
     *,Letter,Smallcaps,1.25,h.sc,*,
     *,Letter,Lowercase,1,x,*,
     *,Letter,Superscript,0.7,ordfeminine,*,</code></pre>
     <p>A <a href="/schriftgestalt/HTSpacer/blob/master/<config-code>code></config-default.py">default config file</a> is provided to make the process easier. You must rename this file so it has the same name as your font plus the <code>_autospace</code> suffix. For example if your file is called <code>myserif.glyphs</code> your config file should be renamed to <code>myserif_autospace.py</code>.</p>
     <p>You can activate or deactivate lines writing a numbersign at the beginning of the line, just as it is in Python language. Each line should contain the 6 values separated by comma, otherwise will result in a traceback error or misconfiguration.</p>
     <p>Once the script is executed on a selection of glyphs, it will output the results in the macro window, displaying if it is using the custom parameters or default parameters and which line of config was applied in each glyph. In this way, you can have control of what the script is doing and if it is applying the line you want.</p>
     <p>If a glyph doesn't match any line, the area parameter will be applied and multiplied proportionally to the glyph height.</p>

   </div>
 </li>

</ul>


<!--

				<li class="accordion-item is-active" data-accordion-item>
  					<a href="#" class="accordion-title">
  						<h5>
  							What do I need to set up to use it?
  						</h5>
  					</a>
  					<div class="accordion-content" data-tab-content>

  					</div>
  				</li>

  			-->
     </div>
   </div>
 </section>